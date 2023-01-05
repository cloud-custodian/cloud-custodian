# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, ChildResourceManager, ChildDescribeSource
from c7n import query
from c7n.filters import ValueFilter
from c7n.utils import local_session, type_schema


def connect_tag_normalize(resources):
    """
    Connect returns tags as a single dict with multiple kv pairs,
    so we need to split it up into a list of single kv pair dicts
    to conform with the common aws format
    """
    for r in resources:
        r['Tags'] = [{'Key': k, 'Value': v} for k, v in r['Tags'].items()]


@resources.register('connect-instance')
class Connect(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'connect'
        enum_spec = ('list_instances', 'InstanceSummaryList', None)
        arn_type = 'instance'
        name = "InstanceAlias"
        id = "Id"


@Connect.filter_registry.register('instance-attribute')
class ConnectInstanceAttributeFilter(ValueFilter):
    """
    Filter Connect resources based on instance attributes

        :example:

    .. code-block:: yaml

            policies:

              - name: connect-instance-attribute
                resource: connect-instance
                filters:
                  - type: instance-attribute
                    key: Attribute.Value
                    value: true
                    attribute_type: CONTACT_LENS

    """

    schema = type_schema('instance-attribute', rinherit=ValueFilter.schema,
        required=['attribute_type'], **{'attribute_type': {'type': 'string'}})
    permissions = ('connect:DescribeInstanceAttribute',)
    annotation_key = 'c7n:InstanceAttribute'

    def process(self, resources, event=None):

        client = local_session(self.manager.session_factory).client('connect')
        results = []

        for r in resources:
            if self.annotation_key not in r:
                instance_attribute = client.describe_instance_attribute(InstanceId=r['Id'],
                                AttributeType=str.upper(self.data.get('attribute_type')))
                r[self.annotation_key] = instance_attribute

            if self.match(r[self.annotation_key]):
                results.append(r)

        return results


class ConnectResourceDescribeSource(ChildDescribeSource):

    def map_parent_child(self, resources):
        parent_child_map = {}

        for r in resources:
            arn = r['Arn']
            _, ident = arn.rsplit(':', 1)
            parts = ident.split('/', 4)
            parent_child_map.setdefault(parts[1], []).append(parts[3])

        return parent_child_map

    def augment(self, resources):
        parent_child_map = self.map_parent_child(resources)
        results = []
        with self.manager.executor_factory(
                max_workers=self.manager.max_workers) as w:
            client = local_session(self.manager.session_factory).client('connect')
            futures = {}
            for instance_id, r_id in parent_child_map.items():
                futures[
                    w.submit(
                        self.process_connect_resources, client, r_id, instance_id)
                ] = (instance_id, r_id)
            for f in futures:
                instance_id, r_id = futures[f]
                if f.exception():
                    self.manager.log.warning(
                        'error fetching connect resources for instance %s: %s',
                        instance_id, f.exception())
                    continue
                results.extend(f.result())
        return results


@query.sources.register('describe-connect-user')
class ConnectUserDescribeSource(ConnectResourceDescribeSource):
    def process_connect_resources(self, client, user_ids, instance_id):

        results = []
        for user_id in user_ids:
            results.append(
                client.describe_user(
                    UserId=user_id,
                    InstanceId=instance_id).get('User', {})
            )
        connect_tag_normalize(results)
        return results


@resources.register('connect-user')
class ConnectUser(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'connect'
        enum_spec = ('list_users', 'UserSummaryList', None)
        parent_spec = ('connect-instance', 'InstanceId', None)
        arn = 'Arn'
        arn_service = 'connect'
        name = "Username"
        id = "Id"
        universal_taggable = object()

    source_mapping = {'describe-child': ConnectUserDescribeSource}


@query.sources.register('describe-connect-routing-profile')
class ConnectRoutingProfileDescribeSource(ConnectResourceDescribeSource):
    def process_connect_resources(self, client, rp_ids, instance_id):

        results = []
        for rp_id in rp_ids:
            results.append(
                client.describe_routing_profile(
                    InstanceId=instance_id,
                    RoutingProfileId=rp_id).get('RoutingProfile', {})
            )
        connect_tag_normalize(results)
        return results


@resources.register('connect-routing-profile')
class ConnectRoutingProfile(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'connect'
        enum_spec = ('list_routing_profiles', 'RoutingProfileSummaryList', None)
        parent_spec = ('connect-instance', 'InstanceId', None)
        arn = 'RoutingProfileArn'
        arn_service = 'connect'
        name = "Name"
        id = "RoutingProfileId"
        universal_taggable = object()

    source_mapping = {'describe-child': ConnectRoutingProfileDescribeSource}


@query.sources.register('describe-connect-queue')
class ConnectQueueDescribeSource(ConnectResourceDescribeSource):

    def process_connect_resources(self, client, q_ids, instance_id):

        results = []
        for q_id in q_ids:
            results.append(
                client.describe_queue(
                    InstanceId=instance_id,
                    QueueId=q_id).get('Queue', {})
            )
        connect_tag_normalize(results)
        return results


@resources.register('connect-queue')
class ConnectQueue(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'connect'
        # Only querying for standard queues because agent queues don't work with describe call
        enum_spec = ('list_queues', 'QueueSummaryList', {'QueueTypes': ['STANDARD']})
        parent_spec = ('connect-instance', 'InstanceId', None)
        arn = 'QueueArn'
        arn_service = 'connect'
        name = "Name"
        id = "QueueId"
        universal_taggable = object()

    source_mapping = {'describe-child': ConnectQueueDescribeSource}


@query.sources.register('describe-connect-quick-connect')
class ConnectQuickConnectDescribeSource(ConnectResourceDescribeSource):

    def process_connect_resources(self, client, qc_ids, instance_id):

        results = []
        for qc_id in qc_ids:
            results.append(
                client.describe_quick_connect(
                    InstanceId=instance_id,
                    QuickConnectId=qc_id).get('QuickConnect', {})
            )
        connect_tag_normalize(results)
        return results


@resources.register('connect-quick-connect')
class ConnectQuickConnect(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'connect'
        enum_spec = ('list_quick_connects', 'QuickConnectSummaryList', None)
        parent_spec = ('connect-instance', 'InstanceId', None)
        arn = 'QuickConnectARN'
        arn_service = 'connect'
        name = "Name"
        id = "QuickConnectId"
        universal_taggable = object()

    source_mapping = {'describe-child': ConnectQuickConnectDescribeSource}


@query.sources.register('describe-connect-contact-flow')
class ConnectContactFlowDescribeSource(ConnectResourceDescribeSource):

    def process_connect_resources(self, client, cf_ids, instance_id):

        results = []
        for cf_id in cf_ids:
            results.append(
                client.describe_contact_flow(
                    InstanceId=instance_id,
                    ContactFlowId=cf_id).get('ContactFlow', {})
            )
        connect_tag_normalize(results)
        return results


@resources.register('connect-contact-flow')
class ConnectContactFlow(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'connect'
        enum_spec = ('list_contact_flows', 'ContactFlowSummaryList', None)
        parent_spec = ('connect-instance', 'InstanceId', None)
        arn = 'Arn'
        arn_service = 'connect'
        name = "Name"
        id = "Id"
        universal_taggable = object()

    source_mapping = {'describe-child': ConnectContactFlowDescribeSource}


@query.sources.register('describe-connect-agent-status')
class ConnectAgentStatusDescribeSource(ConnectResourceDescribeSource):

    def process_connect_resources(self, client, as_ids, instance_id):

        results = []
        for as_id in as_ids:
            results.append(
                client.describe_agent_status(
                    InstanceId=instance_id,
                    AgentStatusId=as_id).get('AgentStatus', {})
            )
        connect_tag_normalize(results)
        return results


@resources.register('connect-agent-status')
class ConnectAgentStatus(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'connect'
        enum_spec = ('list_agent_statuses', 'AgentStatusSummaryList', None)
        parent_spec = ('connect-instance', 'InstanceId', None)
        arn = 'AgentStatusARN'
        arn_service = 'connect'
        name = "Name"
        id = "AgentStatusId"
        universal_taggable = object()

    source_mapping = {'describe-child': ConnectAgentStatusDescribeSource}


@query.sources.register('describe-connect-hours-of-operation')
class ConnectHoursOfOperationDescribeSource(ConnectResourceDescribeSource):

    def process_connect_resources(self, client, hoo_ids, instance_id):

        results = []
        for hoo_id in hoo_ids:
            results.append(
                client.describe_hours_of_operation(
                    InstanceId=instance_id,
                    HoursOfOperationId=hoo_id).get('HoursOfOperation', {})
            )
        connect_tag_normalize(results)
        return results


@resources.register('connect-hours-of-operation')
class ConnectHoursOfOperation(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'connect'
        enum_spec = ('list_hours_of_operations', 'HoursOfOperationSummaryList', None)
        parent_spec = ('connect-instance', 'InstanceId', None)
        arn = 'HoursOfOperationArn'
        arn_service = 'connect'
        name = "Name"
        id = "HoursOfOperationId"
        universal_taggable = object()

    source_mapping = {'describe-child': ConnectHoursOfOperationDescribeSource}


@query.sources.register('describe-connect-phone-number')
class ConnectPhoneNumberDescribeSource(ConnectResourceDescribeSource):

    def process_connect_resources(self, client, pn_ids, instance_id):
        results = []
        for pn_id in pn_ids:
            results.append(
                client.describe_phone_number(
                    PhoneNumberId=pn_id
                ).get('ClaimedPhoneNumberSummary', {})
            )
        connect_tag_normalize(results)
        return results


@resources.register('connect-phone-number')
class ConnectPhoneNumber(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'connect'
        enum_spec = ('list_phone_numbers', 'PhoneNumberSummaryList', None)
        parent_spec = ('connect-instance', 'InstanceId', None)
        arn = 'PhoneNumberArn'
        arn_service = 'connect'
        name = "PhoneNumber"
        id = "PhoneNumberId"
        universal_taggable = object()

    source_mapping = {'describe-child': ConnectPhoneNumberDescribeSource}
