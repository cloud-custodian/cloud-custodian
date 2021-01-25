# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import hashlib
import operator

from c7n.actions import Action
from c7n.exceptions import PolicyValidationError
from c7n.filters import Filter
from c7n.query import QueryResourceManager, TypeInfo
from c7n.manager import resources
from c7n.tags import universal_augment
from c7n.utils import chunks, get_retry, local_session, type_schema, filter_empty
from c7n.version import version

from .aws import shape_validate
from .ec2 import EC2


@resources.register('ssm-parameter')
class SSMParameter(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'ssm'
        enum_spec = ('describe_parameters', 'Parameters', None)
        name = "Name"
        id = "Name"
        universal_taggable = True
        arn_type = "parameter"
        cfn_type = 'AWS::SSM::Parameter'

    retry = staticmethod(get_retry(('Throttled',)))
    permissions = ('ssm:GetParameters',
                   'ssm:DescribeParameters')

    augment = universal_augment


@SSMParameter.action_registry.register('delete')
class DeleteParameter(Action):

    schema = type_schema('delete')
    permissions = ("ssm:DeleteParameter",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ssm')
        for r in resources:
            self.manager.retry(
                client.delete_parameter, Name=r['Name'],
                ignore_err_codes=('ParameterNotFound',))


@resources.register('ssm-managed-instance')
class ManagedInstance(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'ssm'
        enum_spec = ('describe_instance_information', 'InstanceInformationList', None)
        id = 'InstanceId'
        name = 'Name'
        date = 'RegistrationDate'
        arn_type = "managed-instance"

    permissions = ('ssm:DescribeInstanceInformation',)


@EC2.action_registry.register('send-command')
@ManagedInstance.action_registry.register('send-command')
class SendCommand(Action):
    """Run an SSM Automation Document on an instance.

    :Example:

    Find ubuntu 18.04 instances are active with ssm.

    .. code-block:: yaml

        policies:
          - name: ec2-osquery-install
            resource: ec2
            filters:
              - type: ssm
                key: PingStatus
                value: Online
              - type: ssm
                key: PlatformName
                value: Ubuntu
              - type: ssm
                key: PlatformVersion
                value: 18.04
            actions:
              - type: send-command
                command:
                  DocumentName: AWS-RunShellScript
                  Parameters:
                    commands:
                      - wget https://pkg.osquery.io/deb/osquery_3.3.0_1.linux.amd64.deb
                      - dpkg -i osquery_3.3.0_1.linux.amd64.deb
    """

    schema = type_schema(
        'send-command',
        command={'type': 'object'},
        required=('command',))

    permissions = ('ssm:SendCommand',)
    shape = "SendCommandRequest"
    annotation = 'c7n:SendCommand'

    def validate(self):
        shape_validate(self.data['command'], self.shape, 'ssm')
        # If used against an ec2 resource, require an ssm status filter
        # to ensure that we're not trying to send commands to instances
        # that aren't in ssm.
        if self.manager.type != 'ec2':
            return

        found = False
        for f in self.manager.iter_filters():
            if f.type == 'ssm':
                found = True
                break
        if not found:
            raise PolicyValidationError(
                "send-command requires use of ssm filter on ec2 resources")

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ssm')
        for resource_set in chunks(resources, 50):
            self.process_resource_set(client, resource_set)

    def process_resource_set(self, client, resources):
        command = dict(self.data['command'])
        command['InstanceIds'] = [
            r['InstanceId'] for r in resources]
        result = client.send_command(**command).get('Command')
        for r in resources:
            r.setdefault('c7n:SendCommand', []).append(result['CommandId'])


@resources.register('ssm-activation')
class SSMActivation(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'ssm'
        enum_spec = ('describe_activations', 'ActivationList', None)
        id = 'ActivationId'
        name = 'Description'
        date = 'CreatedDate'
        arn = False

    permissions = ('ssm:DescribeActivations',)


@SSMActivation.action_registry.register('delete')
class DeleteSSMActivation(Action):
    schema = type_schema('delete')
    permissions = ('ssm:DeleteActivation',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ssm')
        for a in resources:
            client.delete_activation(ActivationId=a["ActivationId"])


@resources.register('ops-item')
class OpsItem(QueryResourceManager):
    """Resource for OpsItems in SSM OpsCenter
    https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter.html
    """
    class resource_type(TypeInfo):

        enum_spec = ('describe_ops_items', 'OpsItemSummaries', None)
        service = 'ssm'
        arn_type = 'opsitem'
        id = 'OpsItemId'
        name = 'Title'

        default_report_fields = (
            'Status', 'Title', 'LastModifiedTime',
            'CreatedBy', 'CreatedTime')

    QueryKeys = {
        'Status',
        'CreatedBy',
        'Source',
        'Priority',
        'Title',
        'OpsItemId',
        'CreatedTime',
        'LastModifiedTime',
        'OperationalData',
        'OperationalDataKey',
        'OperationalDataValue',
        'ResourceId',
        'AutomationId'}
    QueryOperators = {'Equal', 'LessThan', 'GreaterThan', 'Contains'}

    def validate(self):
        self.query = self.resource_query()
        return super(OpsItem, self).validate()

    def get_resources(self, ids, cache=True, augment=True):
        if isinstance(ids, str):
            ids = [ids]
        return self.resources({
            'OpsItemFilters': [{
                'Key': 'OpsItemId',
                'Values': [i],
                'Operator': 'Equal'} for i in ids]})

    def resources(self, query=None):
        q = self.resource_query()
        if q and query and 'OpsItemFilters' in query:
            q['OpsItemFilters'].extend(query['OpsItemFilters'])
        return super(OpsItem, self).resources(query=q)

    def resource_query(self):
        filters = []
        for q in self.data.get('query', ()):
            if (not isinstance(q, dict) or
                not set(q.keys()) == {'Key', 'Values', 'Operator'} or
                q['Key'] not in self.QueryKeys or
                    q['Operator'] not in self.QueryOperators):
                raise PolicyValidationError(
                    "invalid ops-item query %s" % self.data['query'])
            filters.append(q)
        return {'OpsItemFilters': filters}


@OpsItem.action_registry.register('update')
class UpdateOpsItem(Action):
    """Update an ops item.

    : example :

    Close out open ops items older than 30 days for a given issue.

    .. code-block:: yaml

      policies:
       - name: issue-items
         resource: aws.ops-item
         filters:
          - Status: Open
          - Title: checking-lambdas
          - type: value
            key: CreatedTime
            value_type: age
            op: greater-than
            value: 30
         actions:
          - type: update
            status: Resolved
    """

    schema = type_schema(
        'update',
        description={'type': 'string'},
        priority={'enum': list(range(1, 6))},
        title={'type': 'string'},
        topics={'type': 'array', 'items': {'type': 'string'}},
        status={'enum': ['Open', 'In Progress', 'Resolved']},
    )
    permissions = ('ssm:UpdateOpsItem',)

    def process(self, resources):
        attrs = dict(self.data)
        attrs = filter_empty({
            'Description': attrs.get('description'),
            'Title': attrs.get('title'),
            'Priority': attrs.get('priority'),
            'Status': attrs.get('status'),
            'Notifications': [{'Arn': a} for a in attrs.get('topics', ())]})

        modified = []
        for r in resources:
            for k, v in attrs.items():
                if k not in r or r[k] != v:
                    modified.append(r)

        self.log.debug("Updating %d of %d ops items", len(modified), len(resources))
        client = local_session(self.manager.session_factory).client('ssm')
        for m in modified:
            client.update_ops_item(OpsItemId=m['OpsItemId'], **attrs)


class OpsItemFilter(Filter):
    """Filter resources associated to extant OpsCenter operational items.

    :example:

    Find ec2 instances with open ops items.

    .. code-block:: yaml

       policies:
         - name: ec2-instances-ops-items
           resource: ec2
           filters:
             - type: ops-item
               # we can filter on source, title, priority
               priority: [1, 2]
    """

    schema = type_schema(
        'ops-item',
        status={'type': 'array',
                'default': ['Open'],
                'items': {'enum': ['Open', 'In progress', 'Resolved']}},
        priority={'type': 'array', 'items': {'enum': list(range(1, 6))}},
        title={'type': 'string'},
        source={'type': 'string'})
    schema_alias = True
    permissions = ('ssm:DescribeOpsItems',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ssm')
        results = []

        for resource_set in chunks(resources, 10):
            qf = self.get_query_filter(resource_set)
            items = client.describe_ops_items(**qf).get('OpsItemSummaries')

            arn_item_map = {}
            for i in items:
                for arn in json.loads(
                        i['OperationalData']['/aws/resources']['Value']):
                    arn_item_map.setdefault(arn['arn'], []).append(i['OpsItemId'])

            for arn, r in zip(self.manager.get_arns(resource_set), resource_set):
                if arn in arn_item_map:
                    r['c7n:opsitems'] = arn_item_map[arn]
                    results.append(r)
        return results

    def get_query_filter(self, resources):
        q = []
        q.append({'Key': 'Status', 'Operator': 'Equal',
                  'Values': self.data.get('status', ('Open',))})
        if self.data.get('priority'):
            q.append({'Key': 'Priority', 'Operator': 'Equal',
                      'Values': list(map(str, self.data['priority']))})
        if self.data.get('title'):
            q.append({'Key': 'Title', 'Operator': 'Contains',
                      'Values': [self.data['title']]})
        if self.data.get('source'):
            q.append({'Key': 'Source', 'Operator': 'Equal',
                      'Values': [self.data['source']]})
        q.append({'Key': 'ResourceId', 'Operator': 'Contains',
                  'Values': [r[self.manager.resource_type.id] for r in resources]})
        return {'OpsItemFilters': q}

    @classmethod
    def register_resource(cls, registry, resource_class):
        if 'ops-item' not in resource_class.filter_registry:
            resource_class.filter_registry.register('ops-item', cls)


resources.subscribe(OpsItemFilter.register_resource)


class PostItem(Action):
    """Post an OpsItem to AWS Systems Manager OpsCenter Dashboard.

    https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter.html

    Each ops item supports up to a 100 associated resources. This
    action supports the builtin OpsCenter dedup logic with additional
    support for associating new resources to existing Open ops items.

    : Example :

    Create an ops item for ec2 instances with Create User permissions

    .. code-block:: yaml

        policies:
          - name: over-privileged-ec2
            resource: aws.ec2
            filters:
              - type: check-permissions
                match: allowed
                actions:
                  - iam:CreateUser
            actions:
              - type: post-item
                priority: 3

    The builtin OpsCenter dedup logic will kick in if the same
    resource set (ec2 instances in this case) is posted for the same
    policy.

    : Example :

    Create an ops item for sqs queues with cross account access as ops items.

    .. code-block:: yaml

        policies:
          - name: sqs-cross-account-access
            resource: aws.sqs
            filters:
              - type: cross-account
            actions:
              - type: mark-for-op
                days: 5
                op: delete
              - type: post-item
                title: SQS Cross Account Access
                description: |
                  Cross Account Access detected in SQS resource IAM Policy.
                tags:
                  Topic: Security
    """

    schema = type_schema(
        'post-item',
        description={'type': 'string'},
        tags={'type': 'object'},
        priority={'enum': list(range(1, 6))},
        title={'type': 'string'},
        topics={'type': 'string'},
    )
    schema_alias = True
    permissions = ('ssm:CreateOpsItem',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ssm')
        item_template = self.get_item_template()
        resources = list(sorted(resources, key=operator.itemgetter(
            self.manager.resource_type.id)))
        items = self.get_items(client, item_template)
        if items:
            # - Use a copy of the template as we'll be passing in status changes on updates.
            # - The return resources will be those that we couldn't fit into updates
            #   to existing resources.
            resources = self.update_items(client, items, dict(item_template), resources)

        item_ids = [i['OpsItemId'] for i in items[:5]]

        for resource_set in chunks(resources, 100):
            resource_arns = json.dumps(
                [{'arn': arn} for arn in sorted(self.manager.get_arns(resource_set))])
            item_template['OperationalData']['/aws/resources'] = {
                'Type': 'SearchableString', 'Value': resource_arns}
            if items:
                item_template['RelatedOpsItems'] = [
                    {'OpsItemId': item_ids[:5]}]
            try:
                oid = client.create_ops_item(**item_template).get('OpsItemId')
                item_ids.insert(0, oid)
            except client.exceptions.OpsItemAlreadyExistsException:
                pass

            for r in resource_set:
                r['c7n:opsitem'] = oid

    def get_items(self, client, item_template):
        qf = [
            {'Key': 'OperationalDataValue',
             'Operator': 'Contains',
             'Values': [item_template['OperationalData'][
                 '/custodian/dedup']['Value']]},
            {'Key': 'OperationalDataKey',
             'Operator': 'Equal',
             'Values': ['/custodian/dedup']},
            {'Key': 'Status',
             'Operator': 'Equal',
             # In progress could imply activity/executions underway, we don't want to update
             # the resource set out from underneath that so only look at Open state.
             'Values': ['Open']},
            {'Key': 'Source',
             'Operator': 'Equal',
             'Values': ['Cloud Custodian']}]
        items = client.describe_ops_items(OpsItemFilters=qf)['OpsItemSummaries']
        return list(sorted(items, key=operator.itemgetter('CreatedTime'), reverse=True))

    def update_items(self, client, items, item_template, resources):
        """Update existing Open OpsItems with new resources.

        Originally this tried to support attribute updates as well, but
        the reasoning around that is a bit complex due to partial state
        evaluation around any given execution, so its restricted atm
        to just updating associated resources.

        For management of ops items, use a policy on the
        ops-item resource.

        Rationale: Typically a custodian policy will be evaluating
        some partial set of resources at any given execution (ie think
        a lambda looking at newly created resources), where as a
        collection of ops center items will represent the total
        set. Custodian can multiplex the partial set of resource over
        a set of ops items (100 resources per item) which minimizes
        the item count. When updating the state of an ops item though,
        we have to contend with the possibility that we're doing so
        with only a partial state. Which could be confusing if we
        tried to set the Status to Resolved even if we're only evaluating
        a handful of resources associated to an ops item.
        """
        arn_item_map = {}
        item_arn_map = {}
        for i in items:
            item_arn_map[i['OpsItemId']] = arns = json.loads(
                i['OperationalData']['/aws/resources']['Value'])
            for arn in arns:
                arn_item_map[arn['arn']] = i['OpsItemId']

        arn_resource_map = dict(zip(self.manager.get_arns(resources), resources))
        added = set(arn_resource_map).difference(arn_item_map)

        updated = set()
        remainder = []

        # Check for resource additions
        for a in added:
            handled = False
            for i in items:
                if len(item_arn_map[i['OpsItemId']]) >= 100:
                    continue
                item_arn_map[i['OpsItemId']].append({'arn': a})
                updated.add(i['OpsItemId'])
                arn_resource_map[a]['c7n:opsitem'] = i['OpsItemId']
                handled = True
                break
            if not handled:
                remainder.append(a)

        for i in items:
            if not i['OpsItemId'] in updated:
                continue
            i = dict(i)
            for k in ('CreatedBy', 'CreatedTime', 'Source', 'LastModifiedBy',
                      'LastModifiedTime'):
                i.pop(k, None)
            i['OperationalData']['/aws/resources']['Value'] = json.dumps(
                item_arn_map[i['OpsItemId']])
            i['OperationalData'].pop('/aws/dedup', None)
            client.update_ops_item(**i)
        return remainder

    def get_item_template(self):
        title = self.data.get('title', self.manager.data['name']).strip()
        dedup = ("%s %s %s %s" % (
            title,
            self.manager.type,
            self.manager.config.region,
            self.manager.config.account_id)).encode('utf8')
        # size restrictions on this value is 4-20, digest is 32
        dedup = hashlib.md5(dedup).hexdigest()[:20]

        i = dict(
            Title=title,
            Description=self.data.get(
                'description',
                self.manager.data.get(
                    'description',
                    self.manager.data.get('name'))),
            Priority=self.data.get('priority'),
            Source="Cloud Custodian",
            Tags=[{'Key': k, 'Value': v} for k, v in self.data.get(
                'tags', self.manager.data.get('tags', {})).items()],
            Notifications=[{'Arn': a} for a in self.data.get('topics', ())],
            OperationalData={
                '/aws/dedup': {
                    'Type': 'SearchableString',
                    'Value': json.dumps({'dedupString': dedup})},
                '/custodian/execution-id': {
                    'Type': 'String',
                    'Value': self.manager.ctx.execution_id},
                # We need our own dedup string to be able to filter
                # search on it.
                '/custodian/dedup': {
                    'Type': 'SearchableString',
                    'Value': dedup},
                '/custodian/policy': {
                    'Type': 'String',
                    'Value': json.dumps(self.manager.data)},
                '/custodian/version': {
                    'Type': 'String',
                    'Value': version},
                '/custodian/policy-name': {
                    'Type': 'SearchableString',
                    'Value': self.manager.data['name']},
                '/custodian/resource': {
                    'Type': 'SearchableString',
                    'Value': self.manager.type},
            }
        )
        return filter_empty(i)

    @classmethod
    def register_resource(cls, registry, resource_class):
        if 'post-item' not in resource_class.action_registry:
            resource_class.action_registry.register('post-item', cls)


resources.subscribe(PostItem.register_resource)
