# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.filters import ValueFilter, Filter
from c7n.utils import local_session, type_schema
from c7n.actions import Action
from c7n.filters.kms import KmsRelatedFilter


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
                instance_attribute.pop('ResponseMetadata', None)
                r[self.annotation_key] = instance_attribute

            if self.match(r[self.annotation_key]):
                results.append(r)

        return results

    @Connect.action_registry.register("set-attributes")
    class SetAttributes(Action):
        """Set the attributes for the connect resources

        :example:

        .. code-block:: yaml

            policies:
              - name: connect-set-contact-lens
                resource: connect-instance
                filters:
                  - type: instance-attribute
                    key: Attribute.Value
                    value: false
                    attribute_type: CONTACT_LENS
                actions:
                  - type: set-attributes
                    attribute_type: CONTACT_LENS
                    value: true
              - name: connect-disable-contact-lens
                resource: connect-instance
                filters:
                  - type: instance-attribute
                    key: Attribute.Value
                    value: true
                    attribute_type: CONTACT_LENS
                actions:
                  - type: set-attributes
                    attribute_type: CONTACT_LENS
                    value: false
        """
        attributes = ["INBOUND_CALLS", "OUTBOUND_CALLS",
                      "CONTACTFLOW_LOGS", "CONTACT_LENS",
                      "AUTO_RESOLVE_BEST_VOICES", "USE_CUSTOM_TTS_VOICES",
                      "EARLY_MEDIA", "MULTI_PARTY_CONFERENCE",
                      "HIGH_VOLUME_OUTBOUND", "ENHANCED_CONTACT_MONITORING"]
        schema = type_schema("set-attributes", attribute_type={'anyOf': [{'enum': attributes},
                  {'type': 'string'}]}, value={}, required=["value", "attribute_type"])
        permissions = ("connect:UpdateInstanceAttribute",)

        def process(self, resources):
            client = local_session(self.manager.session_factory).client('connect')

            for r in resources:
                client.update_instance_attribute(InstanceId=r["Id"],
                    AttributeType=self.data.get("attribute_type"), Value=self.data.get("value"))


@resources.register('connect-campaign')
class ConnectCampaign(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'connectcampaigns'
        enum_spec = ('list_campaigns', 'campaignSummaryList', None)
        detail_spec = (
            'get_connect_instance_config',
            'connectInstanceId',
            'connectInstanceId',
            None
        )
        arn_type = 'campaign'
        name = "name"
        id = "id"
        permission_prefix = "connect-campaigns"

    permissions = (
        'connect-campaigns:ListCampaigns',
        'connect-campaigns:GetConnectInstanceConfig',
    )


@ConnectCampaign.filter_registry.register('kms-key')
class ConnectCampaignKmsFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'connectInstanceConfig.encryptionConfig.keyArn'


@resources.register('connect-analytics-association')
class ConnectAnalyticsAssociation(QueryResourceManager):
    """Resource manager for Connect Analytics Data Associations.

    """

    class resource_type(TypeInfo):
        service = 'connect'
        arn = id = 'AssociationId'
        name = 'DataSetId'

    def resources(self, query=None):
        """
        Overrides the default resources() method to handle the multi-step
        enumeration required for analytics data associations.
        """
        client = local_session(self.session_factory).client('connect')
        instance_paginator = client.get_paginator('list_instances')
        all_associations = []
        for page in instance_paginator.paginate():
            for instance in page.get('InstanceSummaryList', []):
                response = client.list_analytics_data_associations(InstanceId=instance['Id'])
                all_associations.extend(response.get('Results', []))
        return self.filter_resources(all_associations)


@ConnectAnalyticsAssociation.filter_registry.register('cross-account')
class ConnectAssociationCrossAccountFilter(Filter):
    """Flags all Connect analytics associations that target an external account.
    """
    schema = type_schema('cross-account')
    permissions = ()

    def process(self, resources, event=None):
        current_account_id = self.manager.account_id
        results = []
        for r in resources:
            target_account = r.get('TargetAccountId')
            if target_account and target_account != current_account_id:
                r['c7n:CurrentAccountId'] = current_account_id
                results.append(r)
        return results
