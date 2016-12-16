# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Actions to take on resources
"""
import base64
import logging
import zlib

from botocore.exceptions import ClientError

from c7n.registry import PluginRegistry
from c7n.executor import ThreadPoolExecutor
from c7n import utils
from c7n.version import version as VERSION


class ActionRegistry(PluginRegistry):

    def __init__(self, *args, **kw):
        super(ActionRegistry, self).__init__(*args, **kw)
        self.register('notify', Notify)
        self.register('invoke-lambda', LambdaInvoke)

    def parse(self, data, manager):
        results = []
        for d in data:
            results.append(self.factory(d, manager))
        return results

    def factory(self, data, manager):
        if isinstance(data, dict):
            action_type = data.get('type')
            if action_type is None:
                raise ValueError(
                    "Invalid action type found in %s" % (data))
        else:
            action_type = data
            data = {}

        action_class = self.get(action_type)
        if action_class is None:
            raise ValueError(
                "Invalid action type %s, valid actions %s" % (
                    action_type, self.keys()))
        # Construct a ResourceManager
        return action_class(data, manager).validate()


class BaseAction(object):

    permissions = ()
    metrics = ()

    log = logging.getLogger("custodian.actions")

    executor_factory = ThreadPoolExecutor

    schema = {'type': 'object'}

    def __init__(self, data=None, manager=None, log_dir=None):
        self.data = data or {}
        self.manager = manager
        self.log_dir = log_dir

    def validate(self):
        return self

    @property
    def name(self):
        return self.__class__.__name__.lower()

    def process(self, resources):
        raise NotImplemented(
            "Base action class does not implement behavior")

    def get_permissions(self):
        return self.permissions

    def _run_api(self, cmd, *args, **kw):
        try:
            return cmd(*args, **kw)
        except ClientError, e:
            if (e.response['Error']['Code'] == 'DryRunOperation'
                    and e.response['ResponseMetadata']['HTTPStatusCode'] == 412
                    and 'would have succeeded' in e.message):
                return self.log.info(
                    "Dry run operation %s succeeded" % (
                        self.__class__.__name__.lower()))
            raise

Action = BaseAction


class ModifyGroupsAction(BaseAction):
    """Common actions for modifying security groups on a resource
    
    Can target either physical groups as a list of group ids or
    symbolic groups like 'matched' or 'all'. 'matched' uses
    the annotations of the 'group' interface filter.
    
    Note an interface always gets at least one security group, so
    we also allow specification of an isolation/quarantine group
    that can be specified if there would otherwise be no groups.

    type: modify-security-groups
        add: []
        remove: [] | matched
        isolation-group: sg-xyz
    """

    # THIS ISN"T FAILING FOR modify-groups.... why not?
    properties = {
        'add': {'oneOf': [{'type': 'string'}, {'type': 'array', 'items': 'string'}]},
        'remove': {'oneOf': [
            {'type': 'string'},
            {'type': 'array', 'items': 'string'},
            {'enum': ['matched', 'all']}]},
        'isolation-group': {'oneOf': [{'type': 'string'}, {'type': 'array', 'items': 'string'}]}
    }
    schema = utils.type_schema(
        'modify-security-groups',
        **properties
    )

    def validate(self):
        if 'remove' in self.data:
            if 'isolation-group' not in self.data and 'add' not in self.data:
                raise ValueError('Must specify `isolation-group` or `add` parameters when using the `remove` action')
            if isinstance(self.data['remove'], basestring) and 'sg-' not in self.data['remove']:
                raise ValueError('Must specify a valid security group id for the `remove` parameter')
            if isinstance(self.data['remove']) and any('sg-' not in g for g in self.data['remove']):
                raise ValueError('Must specify valid security group ids for the `remove` parameter')
        if 'add' in self.data:
            if isinstance('add', basestring) and 'sg-' not in self.data['add']:
                raise ValueError('Must specify a valid security group id for the `add` parameter')
            if isinstance('add', list) and any('sg-' not in g for g in self.data['add']):
                raise ValueError('Must specify valid security group ids for the `add` parameter')
        if 'isolation-group' in self.data:
            if isinstance('isolation-group', basestring) and 'sg-' not in self.data['isolation-group']:
                raise ValueError('Must specify a valid security group id for the `isolation-group` parameter')
            if isinstance('isolation-group', list) and any('sg-' not in g for g in self.data['isolation-group']):
                raise ValueError('Must specify valid security group ids for the `isolation-group` parameter')
        if 'add' not in self.data and 'remove' not in self.data:
            raise ValueError('Must specify either `add` or `remove` parameters')

        return self

    def get_groups(self, resources):
        # parse the add, remove, and isolation group params to return the
        # list of security groups that will end up on the resource
        # target_group_ids = self.data.get('groups', 'matched')

        add_target_group_ids = self.data.get('add', None)
        remove_target_group_ids = self.data.get('remove', None)
        isolation_group = self.data.get('isolation-group')
        add_groups = []
        remove_groups = []
        return_groups = []
        interfaces = []
        multiple = False

        # add groups - append sg-id(s) to the ones already on the resource
        # isolation-group - only apply if len(matched-security-groups) == total sgs on resource

        for idx, r in enumerate(resources):
            # single eni resources
            if r.get('Groups'):
                rgroups = [g['GroupId'] for g in r['Groups']]
            # multi-eni resources
            elif r.get('NetworkInterfaces'):
                enis = r['NetworkInterfaces']
                for i in enis:
                    rgroups = [g['GroupId'] for g in i['Groups']]
                    interfaces.append((i['NetworkInterfaceId'], rgroups))
                # rgroups = [g['GroupId'] for i in interfaces for g in i['Groups']]

            if len(interfaces) > 1:
                multiple = True

            # if target_group_ids == 'matched':
            #     group_ids = r.get('c7n.matched-security-groups', ())
            # elif target_group_ids == 'all':
            #     group_ids = rgroups
            # elif isinstance(target_group_ids, list):
            #     group_ids = target_group_ids
            # else:
            #     continue

            # Parse remove_groups
            if remove_target_group_ids == 'matched':
                remove_groups = r.get('c7n.matched-security-groups', ())
            elif remove_target_group_ids == 'all':
                remove_groups = rgroups
            elif isinstance(remove_target_group_ids, list):
                remove_groups = remove_target_group_ids
            elif isinstance(remove_target_group_ids, basestring):
                remove_groups = [remove_target_group_ids]

            # Parse add_groups
            if isinstance(add_target_group_ids, list):
                add_groups = add_target_group_ids
            elif isinstance(add_target_group_ids, basestring):
                add_groups = [add_target_group_ids]

            if not remove_groups and not add_groups:
                continue

            for g in remove_groups:
                if not multiple and g in rgroups:
                    rgroups.remove(g)
                elif multiple and g in rgroups:
                    interfaces[idx][1].remove(g)
            for g in add_groups:
                if not multiple and g not in rgroups:
                    rgroups.append(g)
                elif multiple and g not in rgroups:
                    interfaces[idx][1].append(g)

            if not multiple and not rgroups:
                rgroups.append(isolation_group)
            elif multiple and not interfaces[idx][1]:
                interfaces[idx][1].append(isolation_group)

            if not multiple:
                return_groups.append(rgroups)
            elif multiple:
                return_groups.append(interfaces)

        return return_groups


class EventAction(BaseAction):
    """Actions which receive lambda event if present
    """


class LambdaInvoke(EventAction):
    """ Invoke an arbitrary lambda

    serialized invocation parameters

     - resources / collection of resources
     - policy / policy that is invoke the lambda
     - action / action that is invoking the lambda
     - event / cloud trail event if any
     - version / version of custodian invoking the lambda

    We automatically batch into sets of 250 for invocation,
    We try to utilize async invocation by default, this imposes
    some greater size limits of 128kb which means we batch
    invoke.

    Example::

     - type: invoke-lambda
       function: my-function
    """

    schema = utils.type_schema(
        'invoke-lambda',
        function={'type': 'string'},
        async={'type': 'boolean'},
        qualifier={'type': 'string'},
        batch_size={'type': 'integer'},
        required=('function',))

    def process(self, resources, event=None):
        client = utils.local_session(
            self.manager.session_factory).client('lambda')

        params = dict(FunctionName=self.data['function'])
        if self.data.get('qualifier'):
            params['Qualifier'] = self.data['Qualifier']

        if self.data.get('async', True):
            params['InvocationType'] = 'Event'

        payload = {
            'version': VERSION,
            'event': event,
            'action': self.data,
            'policy': self.manager.data}

        results = []
        for resource_set in utils.chunks(resources, self.data.get('batch_size', 250)):
            payload['resources'] = resource_set
            params['Payload'] = utils.dumps(payload)
            result = client.invoke(**params)
            result['Payload'] = result['Payload'].read()
            results.append(result)
        return results


class Notify(EventAction):
    """
    Flexible notifications require quite a bit of implementation support
    on pluggable transports, templates, address resolution, variable
    extraction, batch periods, etc.

    For expedience and flexibility then, we instead send the data to
    an sqs queue, for processing. ie. actual communications is DIY atm.

    Example::

      policies:
        - name: ec2-bad-instance-kill
          resource: ec2
          filters:
           - Name: bad-instance
          actions:
           - terminate
           - type: notify
             to:
              - event-user
              - resource-creator
              - email@address
             # which template for the email should we use
             template: policy-template
             transport:
               type: sqs
               region: us-east-1
               queue: xyz
    """

    C7N_DATA_MESSAGE = "maidmsg/1.0"

    schema = {
        'type': 'object',
        'required': ['type', 'transport', 'to'],
        'properties': {
            'type': {'enum': ['notify']},
            'to': {'type': 'array', 'items': {'type': 'string'}},
            'cc': {'type': 'array', 'items': {'type': 'string'}},
            'cc_manager': {'type': 'boolean'},
            'from': {'type': 'string'},
            'subject': {'type': 'string'},
            'template': {'type': 'string'},
            'transport': {
                'type': 'object',
                'required': ['type', 'queue'],
                'properties': {
                    'queue': {'type': 'string'},
                    'region': {'type': 'string'},
                    'type': {'enum': ['sqs']}}
            }
        }
    }
    batch_size = 250

    def process(self, resources, event=None):
        aliases = self.manager.session_factory().client(
            'iam').list_account_aliases().get('AccountAliases', ())
        account_name = aliases and aliases[0] or ''
        for batch in utils.chunks(resources, self.batch_size):
            message = {'resources': batch,
                       'event': event,
                       'account': account_name,
                       'action': self.data,
                       'region': self.manager.config.region,
                       'policy': self.manager.data}
            receipt = self.send_data_message(message)
            self.log.info("sent message:%s policy:%s template:%s count:%s" % (
                receipt, self.manager.data['name'],
                self.data.get('template', 'default'), len(batch)))

    def send_data_message(self, message):
        if self.data['transport']['type'] == 'sqs':
            return self.send_sqs(message)

    def send_sqs(self, message):
        queue = self.data['transport']['queue']
        region = queue.split('.', 2)[1]
        client = self.manager.session_factory(region=region).client('sqs')
        attrs = {
            'mtype': {
                'DataType': 'String',
                'StringValue': self.C7N_DATA_MESSAGE,
                },
            }
        result = client.send_message(
            QueueUrl=queue,
            MessageBody=base64.b64encode(zlib.compress(utils.dumps(message))),
            MessageAttributes=attrs)
        return result['MessageId']


class AutoTagUser(EventAction):
    """Tag a resource with the user who created/modified it.

    policies:
      - name: ec2-auto-tag-owner
        resource: ec2
        filters:
         - tag:Owner: absent
        actions:
         - type: auto-tag-creator
           tag: OwnerContact

    There's a number of caveats to usage, resources which don't
    include tagging as part of their api, may have some delay before
    automation kicks in to create a tag. Real world delay may be several
    minutes, with worst case into hours[0]. This creates a race condition
    between auto tagging and automation.

    In practice this window is on the order of a fraction of a second, as
    we fetch the resource and evaluate the presence of the tag before
    attempting to tag it.

    References
     - AWS Config (see REQUIRED_TAGS caveat) - http://goo.gl/oDUXPY
     - CloudTrail User - http://goo.gl/XQhIG6 q
    """

    schema = utils.type_schema(
        'auto-tag',
        required=['tag'],
        **{'user-type': {
            'type': 'array',
            'items': {'type': 'string',
                      'enum': [
                          'IAMUser',
                          'AssumedRole',
                          'FederatedUser'
                      ]}},
           'update': {'type': 'boolean'},
           'tag': {'type': 'string'},
           }
    )

    def validate(self):
        if self.manager.data.get('mode', {}).get('type') != 'cloudtrail':
            raise ValueError("Auto tag owner requires an event")
        if self.manager.action_registry.get('tag') is None:
            raise ValueError("Resources does not support tagging")
        return self

    def process(self, resources, event):
        if event is None:
            return
        event = event['detail']
        utype = event['userIdentity']['type']
        if utype not in self.data.get('user-type', ['AssumedRole', 'IAMUser']):
            return

        user = None
        if utype == "IAMUser":
            user = event['userIdentity']['userName']
        elif utype == "AssumedRole":
            user = event['userIdentity']['arn']
            prefix, user = user.rsplit('/', 1)
            # instance role
            if user.startswith('i-'):
                return
            # lambda function
            elif user.startswith('awslambda'):
                return
        if user is None:
            return
        if not self.data.get('update', False):
            untagged = []
            for r in resources:
                found = False
                for t in r.get('Tags', ()):
                    if t['Key'] == self.data['tag']:
                        found = True
                        break
                if not found:
                    untagged.append(r)
        else:
            untagged = resources

        tag_action = self.manager.action_registry.get('tag')
        tag_action(
            {'key': self.data['tag'], 'value': user},
            self.manager).process(untagged)
        return untagged
