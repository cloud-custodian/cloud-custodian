# Copyright 2015-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

import base64
import copy
from datetime import datetime
import jmespath
import logging
import zlib

import six
from botocore.exceptions import ClientError

from c7n.executor import ThreadPoolExecutor
from c7n.manager import resources
from c7n.registry import PluginRegistry
from c7n.resolver import ValuesFrom
from c7n import utils
from c7n.version import version as VERSION


def average(numbers):
    return float(sum(numbers)) / max(len(numbers), 1)


def distinct_count(values):
    return float(len(set(values)))


METRIC_OPS = {
    'count': len,
    'distinct_count': distinct_count,
    'sum': sum,
    'average': average,
}

METRIC_UNITS = [
    # Time
    'Seconds',
    'Microseconds',
    'Milliseconds',
    # Bytes and Bits
    'Bytes',
    'Kilobytes',
    'Megabytes',
    'Gigabytes',
    'Terabytes',
    'Bits',
    'Kilobits',
    'Megabits',
    'Gigabits',
    'Terabits',
    # Rates
    'Bytes/Second',
    'Kilobytes/Second',
    'Megabytes/Second',
    'Gigabytes/Second',
    'Terabytes/Second',
    'Bits/Second',
    'Kilobits/Second',
    'Megabits/Second',
    'Gigabits/Second',
    'Terabits/Second',
    'Count/Second',
    # Other Scalars
    'Percent',
    'Count',
    'None'
]


class ActionRegistry(PluginRegistry):

    def __init__(self, *args, **kw):
        super(ActionRegistry, self).__init__(*args, **kw)
        self.register('notify', Notify)
        self.register('invoke-lambda', LambdaInvoke)
        self.register('put-metric', PutMetric)

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
                    action_type, list(self.keys())))
        # Construct a ResourceManager
        return action_class(data, manager).validate()


class Action(object):

    permissions = ()
    metrics = ()

    log = logging.getLogger("custodian.actions")

    executor_factory = ThreadPoolExecutor
    permissions = ()
    schema = {'type': 'object'}

    def __init__(self, data=None, manager=None, log_dir=None):
        self.data = data or {}
        self.manager = manager
        self.log_dir = log_dir

    def get_permissions(self):
        return self.permissions

    def validate(self):
        return self

    @property
    def name(self):
        return self.__class__.__name__.lower()

    def process(self, resources):
        raise NotImplementedError(
            "Base action class does not implement behavior")

    def _run_api(self, cmd, *args, **kw):
        try:
            return cmd(*args, **kw)
        except ClientError as e:
            if (e.response['Error']['Code'] == 'DryRunOperation' and
            e.response['ResponseMetadata']['HTTPStatusCode'] == 412 and
            'would have succeeded' in e.response['Error']['Message']):
                return self.log.info(
                    "Dry run operation %s succeeded" % (
                        self.__class__.__name__.lower()))
            raise


BaseAction = Action


class ModifyVpcSecurityGroupsAction(Action):
    """Common actions for modifying security groups on a resource

    Can target either physical groups as a list of group ids or
    symbolic groups like 'matched' or 'all'. 'matched' uses
    the annotations of the 'security-group' interface filter.

    Note an interface always gets at least one security group, so
    we mandate the specification of an isolation/quarantine group
    that can be specified if there would otherwise be no groups.

    type: modify-security-groups
        add: []
        remove: [] | matched
        isolation-group: sg-xyz
    """
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['modify-security-groups']},
            'add': {'oneOf': [
                {'type': 'string', 'pattern': '^sg-*'},
                {'type': 'array', 'items': {
                    'pattern': '^sg-*',
                    'type': 'string'}}]},
            'remove': {'oneOf': [
                {'type': 'array', 'items': {
                    'type': 'string', 'pattern': '^sg-*'}},
                {'enum': [
                    'matched', 'all',
                    {'type': 'string', 'pattern': '^sg-*'}]}]},
            'isolation-group': {'oneOf': [
                {'type': 'string', 'pattern': '^sg-*'},
                {'type': 'array', 'items': {
                    'type': 'string', 'pattern': '^sg-*'}}]}},
        'anyOf': [
            {'required': ['isolation-group', 'remove', 'type']},
            {'required': ['add', 'remove', 'type']},
            {'required': ['add', 'type']}]
    }

    def get_groups(self, resources, metadata_key=None):
        """Parse policies to get lists of security groups to attach to each resource

        For each input resource, parse the various add/remove/isolation-
        group policies for 'modify-security-groups' to find the resulting
        set of VPC security groups to attach to that resource.

        The 'metadata_key' parameter can be used for two purposes at
        the moment; The first use is for resources' APIs that return a
        list of security group IDs but use a different metadata key
        than 'Groups' or 'SecurityGroups'.

        The second use is for when there are richer objects in the 'Groups' or
        'SecurityGroups' lists. The custodian actions need to act on lists of
        just security group IDs, so the metadata_key can be used to select IDs
        from the richer objects in the provided lists.

        Returns a list of lists containing the resulting VPC security groups
        that should end up on each resource passed in.

        :param resources: List of resources containing VPC Security Groups
        :param metadata_key: Metadata key for security groups list
        :return: List of lists of security groups per resource

        """
        # parse the add, remove, and isolation group params to return the
        # list of security groups that will end up on the resource
        # target_group_ids = self.data.get('groups', 'matched')

        add_target_group_ids = self.data.get('add', None)
        remove_target_group_ids = self.data.get('remove', None)
        isolation_group = self.data.get('isolation-group')
        add_groups = []
        remove_groups = []
        return_groups = []

        for idx, r in enumerate(resources):
            if r.get('Groups'):
                if metadata_key and isinstance(r['Groups'][0], dict):
                    rgroups = [g[metadata_key] for g in r['SecurityGroups']]
                else:
                    rgroups = [g['GroupId'] for g in r['Groups']]
            elif r.get('SecurityGroups'):
                # elb, ec2, elasticache, efs, vpc resource security groups
                if metadata_key and isinstance(r['SecurityGroups'][0], dict):
                    rgroups = [g[metadata_key] for g in r['SecurityGroups']]
                else:
                    rgroups = [g for g in r['SecurityGroups']]
            elif r.get('VpcSecurityGroups'):
                # rds resource security groups
                if metadata_key and isinstance(r['VpcSecurityGroups'][0], dict):
                    rgroups = [g[metadata_key] for g in r['VpcSecurityGroups']]
                else:
                    rgroups = [g for g in r['VpcSecurityGroups']]
            elif r.get('VPCOptions', {}).get('SecurityGroupIds', []):
                # elasticsearch resource security groups
                if metadata_key and isinstance(
                        r['VPCOptions']['SecurityGroupIds'][0], dict):
                    rgroups = [g[metadata_key] for g in r[
                        'VPCOptions']['SecurityGroupIds']]
                else:
                    rgroups = [g for g in r['VPCOptions']['SecurityGroupIds']]
            # use as substitution for 'Groups' or '[Vpc]SecurityGroups'
            # unsure if necessary - defer to coverage report
            elif metadata_key and r.get(metadata_key):
                rgroups = [g for g in r[metadata_key]]

            # Parse remove_groups
            if remove_target_group_ids == 'matched':
                remove_groups = r.get('c7n:matched-security-groups', ())
            elif remove_target_group_ids == 'all':
                remove_groups = rgroups
            elif isinstance(remove_target_group_ids, list):
                remove_groups = remove_target_group_ids
            elif isinstance(remove_target_group_ids, six.string_types):
                remove_groups = [remove_target_group_ids]

            # Parse add_groups
            if isinstance(add_target_group_ids, list):
                add_groups = add_target_group_ids
            elif isinstance(add_target_group_ids, six.string_types):
                add_groups = [add_target_group_ids]

            # seems extraneous with list?
            # if not remove_groups and not add_groups:
            #     continue

            for g in remove_groups:
                if g in rgroups:
                    rgroups.remove(g)

            for g in add_groups:
                if g not in rgroups:
                    rgroups.append(g)

            if not rgroups:
                rgroups.append(isolation_group)

            return_groups.append(rgroups)

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

    def get_permissions(self):
        if self.data.get('async', True):
            return ('lambda:InvokeAsync',)
        return ('lambda:Invoke',)

    permissions = ('lambda:InvokeFunction',)

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
             owner_absent_contact:
              - other_email@address
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
        'anyOf': [
            {'required': ['type', 'transport', 'to']},
            {'required': ['type', 'transport', 'to_from']}],
        'properties': {
            'type': {'enum': ['notify']},
            'to': {'type': 'array', 'items': {'type': 'string'}},
            'owner_absent_contact': {'type': 'array', 'items': {'type': 'string'}},
            'to_from': ValuesFrom.schema,
            'cc': {'type': 'array', 'items': {'type': 'string'}},
            'cc_from': ValuesFrom.schema,
            'cc_manager': {'type': 'boolean'},
            'from': {'type': 'string'},
            'subject': {'type': 'string'},
            'template': {'type': 'string'},
            'transport': {
                'oneOf': [
                    {'type': 'object',
                     'required': ['type', 'queue'],
                     'properties': {
                         'queue': {'type': 'string'},
                         'type': {'enum': ['sqs']}}},
                    {'type': 'object',
                     'required': ['type', 'topic'],
                     'properties': {
                         'topic': {'type': 'string'},
                         'type': {'enum': ['sns']},
                     }}]
            },
            'assume_role': {'type': 'boolean'}
        }
    }

    batch_size = 250

    def __init__(self, data=None, manager=None, log_dir=None):
        super(Notify, self).__init__(data, manager, log_dir)
        self.assume_role = data.get('assume_role', True)

    def get_permissions(self):
        if self.data.get('transport', {}).get('type') == 'sns':
            return ('sns:Publish',)
        if self.data.get('transport', {'type': 'sqs'}).get('type') == 'sqs':
            return ('sqs:SendMessage',)
        return ()

    def expand_variables(self, message):
        """expand any variables in the action to_from/cc_from fields.
        """
        p = copy.deepcopy(self.data)
        if 'to_from' in self.data:
            to_from = self.data['to_from'].copy()
            to_from['url'] = to_from['url'].format(**message)
            if 'expr' in to_from:
                to_from['expr'] = to_from['expr'].format(**message)
            p.setdefault('to', []).extend(ValuesFrom(to_from, self.manager).get_values())
        if 'cc_from' in self.data:
            cc_from = self.data['cc_from'].copy()
            cc_from['url'] = cc_from['url'].format(**message)
            if 'expr' in cc_from:
                cc_from['expr'] = cc_from['expr'].format(**message)
            p.setdefault('cc', []).extend(ValuesFrom(cc_from, self.manager).get_values())
        return p

    def process(self, resources, event=None):
        alias = utils.get_account_alias_from_sts(
            utils.local_session(self.manager.session_factory))
        message = {
            'event': event,
            'account_id': self.manager.config.account_id,
            'account': alias,
            'region': self.manager.config.region,
            'policy': self.manager.data}
        message['action'] = self.expand_variables(message)

        for batch in utils.chunks(resources, self.batch_size):
            message['resources'] = batch
            receipt = self.send_data_message(message)
            self.log.info("sent message:%s policy:%s template:%s count:%s" % (
                receipt, self.manager.data['name'],
                self.data.get('template', 'default'), len(batch)))

    def send_data_message(self, message):
        if self.data['transport']['type'] == 'sqs':
            return self.send_sqs(message)
        elif self.data['transport']['type'] == 'sns':
            return self.send_sns(message)

    def pack(self, message):
        dumped = utils.dumps(message)
        compressed = zlib.compress(dumped.encode('utf8'))
        b64encoded = base64.b64encode(compressed)
        return b64encoded.decode('ascii')

    def send_sns(self, message):
        topic = self.data['transport']['topic'].format(**message)
        if topic.startswith('arn:aws:sns'):
            region = region = topic.split(':', 5)[3]
            topic_arn = topic
        else:
            region = message['region']
            topic_arn = "arn:aws:sns:%s:%s:%s" % (
                message['region'], message['account_id'], topic)
        client = self.manager.session_factory(
            region=region, assume=self.assume_role).client('sns')
        attrs = {
            'mtype': {
                'DataType': 'String',
                'StringValue': self.C7N_DATA_MESSAGE,
            },
        }
        client.publish(
            TopicArn=topic_arn,
            Message=self.pack(message),
            MessageAttributes=attrs
        )

    def send_sqs(self, message):
        queue = self.data['transport']['queue'].format(**message)
        if queue.startswith('https://queue.amazonaws.com'):
            region = 'us-east-1'
            queue_url = queue
        elif 'queue.amazonaws.com' in queue:
            region = queue[len('https://'):].split('.', 1)[0]
            queue_url = queue
        elif queue.startswith('https://sqs.'):
            region = queue.split('.', 2)[1]
            queue_url = queue
        elif queue.startswith('arn:aws:sqs'):
            queue_arn_split = queue.split(':', 5)
            region = queue_arn_split[3]
            owner_id = queue_arn_split[4]
            queue_name = queue_arn_split[5]
            queue_url = "https://sqs.%s.amazonaws.com/%s/%s" % (
                region, owner_id, queue_name)
        else:
            region = self.manager.config.region
            owner_id = self.manager.config.account_id
            queue_name = queue
            queue_url = "https://sqs.%s.amazonaws.com/%s/%s" % (
                region, owner_id, queue_name)
        client = self.manager.session_factory(
            region=region, assume=self.assume_role).client('sqs')
        attrs = {
            'mtype': {
                'DataType': 'String',
                'StringValue': self.C7N_DATA_MESSAGE,
            },
        }
        result = client.send_message(
            QueueUrl=queue_url,
            MessageBody=self.pack(message),
            MessageAttributes=attrs)
        return result['MessageId']


class AutoTagUser(EventAction):
    """Tag a resource with the user who created/modified it.

    .. code-block:: yaml

      policies:
        - name: ec2-auto-tag-ownercontact
          resource: ec2
          description: |
            Triggered when a new EC2 Instance is launched. Checks to see if
            it's missing the OwnerContact tag. If missing it gets created
            with the value of the ID of whomever called the RunInstances API
          mode:
            type: cloudtrail
            role: arn:aws:iam::123456789000:role/custodian-auto-tagger
            events:
              - RunInstances
          filters:
           - tag:OwnerContact: absent
          actions:
           - type: auto-tag-user
             tag: OwnerContact

    There's a number of caveats to usage. Resources which don't
    include tagging as part of their api may have some delay before
    automation kicks in to create a tag. Real world delay may be several
    minutes, with worst case into hours[0]. This creates a race condition
    between auto tagging and automation.

    In practice this window is on the order of a fraction of a second, as
    we fetch the resource and evaluate the presence of the tag before
    attempting to tag it.

    References
     - AWS Config (see REQUIRED_TAGS caveat) - http://goo.gl/oDUXPY
     - CloudTrail User - http://goo.gl/XQhIG6
    """

    schema = utils.type_schema(
        'auto-tag-user',
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
           'principal_id_tag': {'type': 'string'}
           }
    )

    def get_permissions(self):
        return self.manager.action_registry.get(
            'tag')({}, self.manager).get_permissions()

    def validate(self):
        if self.manager.data.get('mode', {}).get('type') != 'cloudtrail':
            raise ValueError("Auto tag owner requires an event")
        if self.manager.action_registry.get('tag') is None:
            raise ValueError("Resource does not support tagging")
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
            principal_id_value = event['userIdentity'].get('principalId', '')
        elif utype == "AssumedRole":
            user = event['userIdentity']['arn']
            prefix, user = user.rsplit('/', 1)
            principal_id_value = event['userIdentity'].get('principalId', '').split(':')[0]
            # instance role
            if user.startswith('i-'):
                return
            # lambda function (old style)
            elif user.startswith('awslambda'):
                return
        if user is None:
            return
        # if the auto-tag-user policy set update to False (or it's unset) then we
        # will skip writing their UserName tag and not overwrite pre-existing values
        if not self.data.get('update', False):
            untagged_resources = []
            # iterating over all the resources the user spun up in this event
            for resource in resources:
                tag_already_set = False
                for tag in resource.get('Tags', ()):
                    if tag['Key'] == self.data['tag']:
                        tag_already_set = True
                        break
                if not tag_already_set:
                    untagged_resources.append(resource)
        # if update is set to True, we will overwrite the userName tag even if
        # the user already set a value
        else:
            untagged_resources = resources

        tag_action = self.manager.action_registry.get('tag')
        new_tags = {
            self.data['tag']: user
        }
        # if principal_id_key is set (and value), we'll set the principalId tag.
        principal_id_key = self.data.get('principal_id_tag', None)
        if principal_id_key and principal_id_value:
            new_tags[principal_id_key] = principal_id_value
        for key, value in six.iteritems(new_tags):
            tag_action({'key': key, 'value': value}, self.manager).process(untagged_resources)
        return new_tags


def add_auto_tag_user(registry, _):
    for resource in registry.keys():
        klass = registry.get(resource)
        if klass.action_registry.get('tag') and not klass.action_registry.get('auto-tag-user'):
            klass.action_registry.register('auto-tag-user', AutoTagUser)


resources.subscribe(resources.EVENT_FINAL, add_auto_tag_user)


class PutMetric(BaseAction):
    """Action to put metrics based on an expression into CloudWatch metrics

    :example:

    .. code-block:: yaml

            policies:
              - name: track-attached-ebs
                resource: ec2
                comment: |
                  Put the count of the number of EBS attached disks to an instance
                filters:
                  - Name: tracked-ec2-instance
                actions:
                  - type: put-metric
                    key: Reservations[].Instances[].BlockDeviceMappings[].DeviceName
                    namespace: Usage Metrics
                    metric_name: Attached Disks
                    op: count
                    units: Files

    op and units are optional and will default to simple Counts.
    """
    # permissions are typically lowercase servicename:TitleCaseActionName
    permissions = {'cloudwatch:PutMetricData', }
    schema = {
        'type': 'object',
        'required': ['type', 'key', 'namespace', 'metric_name'],
        'properties': {
            'type': {'enum': ['put-metric', ]},
            'key': {'type': 'string'},  # jmes path
            'namespace': {'type': 'string'},
            'metric_name': {'type': 'string'},
            'dimensions':
                {'type':'array',
                'items': {
                    'type':'object'
                },
            },
            'op': {'enum': list(METRIC_OPS.keys())},
            'units': {'enum': METRIC_UNITS}
        }
    }

    def process(self, resources):
        ns = self.data['namespace']
        metric_name = self.data['metric_name']
        key_expression = self.data.get('key', 'Resources[]')
        operation = self.data.get('op', 'count')
        units = self.data.get('units', 'Count')
        # dimensions are passed as a list of dicts
        dimensions = self.data.get('dimensions', [])

        now = datetime.utcnow()

        # reduce the resources by the key expression, and apply the operation to derive the value
        values = []
        self.log.debug("searching for %s in %s", key_expression, resources)
        try:
            values = jmespath.search("Resources[]." + key_expression,
                                     {'Resources': resources})
            # I had to wrap resourses in a dict like this in order to not have jmespath expressions
            # start with [] in the yaml files.  It fails to parse otherwise.
        except TypeError as oops:
            self.log.error(oops.message)

        value = 0
        try:
            f = METRIC_OPS[operation]
            value = f(values)
        except KeyError:
            self.log.error("Bad op for put-metric action: %s", operation)

        # for demo purposes
        # from math import sin, pi
        # value = sin((now.minute * 6 * 4 * pi) / 180) * ((now.hour + 1) * 4.0)

        metrics_data = [
            {
                'MetricName': metric_name,
                'Dimensions': [{'Name': i[0], 'Value': i[1]}
                               for d in dimensions
                               for i in d.items()],
                'Timestamp': now,
                'Value': value,
                # TODO: support an operation of 'stats' to include this
                # structure instead of a single Value
                # Value and StatisticValues are mutually exclusive.
                # 'StatisticValues': {
                #     'SampleCount': 1,
                #     'Sum': 123.0,
                #     'Minimum': 123.0,
                #     'Maximum': 123.0
                # },
                'Unit': units,
            },
        ]

        client = self.manager.session_factory().client('cloudwatch')
        client.put_metric_data(Namespace=ns, MetricData=metrics_data)

        return resources


class RemovePolicyBase(BaseAction):

    schema = utils.type_schema(
        'remove-statements',
        required=['statement_ids'],
        statement_ids={'oneOf': [
            {'enum': ['matched']},
            {'type': 'array', 'items': {'type': 'string'}}]})

    def process_policy(self, policy, resource, matched_key):
        statements = policy.get('Statement', [])
        resource_statements = resource.get(matched_key, ())

        return remove_statements(
            self.data['statement_ids'], statements, resource_statements)


def remove_statements(match_ids, statements, matched=()):
    found = []
    for s in list(statements):
        s_found = False
        if match_ids == '*':
            s_found = True
        elif match_ids == 'matched':
            if s in matched:
                s_found = True
        elif s['Sid'] in match_ids:
            s_found = True
        if s_found:
            found.append(s)
            statements.remove(s)
    if not found:
        return None, found
    return statements, found


class ModifyPolicyBase(BaseAction):

    schema = utils.type_schema(
        'modify-policy',
        **{
            'add-statements': {
                'type': 'array',
                'required': True,
                'items': {'$ref': '#/definitions/iam-statement'},
                'additionalProperties': False
            },
            'remove-statements': {
                'type': ['array', 'string'],
                'oneOf': [
                    {'enum': ['matched', '*']},
                    {'type': 'array', 'items': {'type': 'string'}}
                ],
                'required': True,
                'additionalProperties': False
            }
        }
    )

    def __init__(self, data=None, manager=None):
        if manager is not None:
            config_args = {
                'account_id': manager.config.account_id,
                'region': manager.config.region
            }
            self.data = utils.format_string_values(data, **config_args)
        else:
            self.data = utils.format_string_values(data)
        self.manager = manager

    def add_statements(self, policy_statements):
        current = {s['Sid']: s for s in policy_statements}
        additional = {s['Sid']: s for s in self.data.get('add-statements', [])}
        current.update(additional)
        return list(current.values()), bool(additional)

    def remove_statements(self, policy_statements, resource, matched_key):
        statement_ids = self.data.get('remove-statements', [])
        found = []
        if len(statement_ids) == 0:
            return policy_statements, found
        resource_statements = resource.get(matched_key, ())
        return remove_statements(
            statement_ids, policy_statements, resource_statements)
