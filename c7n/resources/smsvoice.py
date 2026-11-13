# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import DescribeWithResourceTags, QueryResourceManager, TypeInfo
from c7n.utils import local_session


@resources.register('sms-voice-phone-number')
class SmsVoicePhoneNumber(QueryResourceManager):
    """AWS End User Messaging SMS - Phone Number

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-prod-phone-number-deletion-protection
            resource: aws.sms-voice-phone-number
            filters:
              - tag:Environment: prod
              - DeletionProtectionEnabled: false
    """

    class resource_type(TypeInfo):
        service = 'pinpoint-sms-voice-v2'
        permission_prefix = 'sms-voice'
        # Owner=SELF excludes phone numbers shared into the account by others
        enum_spec = ('describe_phone_numbers', 'PhoneNumbers', {'Owner': 'SELF'})
        id = 'PhoneNumberId'
        name = 'PhoneNumber'
        arn = 'PhoneNumberArn'
        date = 'CreatedTimestamp'
        cfn_type = 'AWS::SMSVOICE::PhoneNumber'
        universal_taggable = object()

    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('sms-voice-sender-id')
class SmsVoiceSenderId(QueryResourceManager):
    """AWS End User Messaging SMS - Sender ID

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-sender-id-unregistered
            resource: aws.sms-voice-sender-id
            filters:
              - Registered: false
    """

    class resource_type(TypeInfo):
        service = 'pinpoint-sms-voice-v2'
        permission_prefix = 'sms-voice'
        enum_spec = ('describe_sender_ids', 'SenderIds', {'Owner': 'SELF'})
        # a sender id is only unique per country, so key on the arn
        id = arn = 'SenderIdArn'
        name = 'SenderId'
        cfn_type = 'AWS::SMSVOICE::SenderId'
        universal_taggable = object()

    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('sms-voice-pool')
class SmsVoicePool(QueryResourceManager):
    """AWS End User Messaging SMS - Phone Pool

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-pool-self-managed-opt-outs
            resource: aws.sms-voice-pool
            filters:
              - or:
                - SelfManagedOptOutsEnabled: true
                - OptOutListName: absent
    """

    class resource_type(TypeInfo):
        service = 'pinpoint-sms-voice-v2'
        permission_prefix = 'sms-voice'
        enum_spec = ('describe_pools', 'Pools', {'Owner': 'SELF'})
        id = name = 'PoolId'
        arn = 'PoolArn'
        date = 'CreatedTimestamp'
        cfn_type = 'AWS::SMSVOICE::Pool'
        universal_taggable = object()

    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('sms-voice-configuration-set')
class SmsVoiceConfigurationSet(QueryResourceManager):
    """AWS End User Messaging SMS - Configuration Set

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-configuration-set-message-feedback
            resource: aws.sms-voice-configuration-set
            filters:
              - tag:Environment: prod
              - DefaultMessageFeedbackEnabled: false
    """

    class resource_type(TypeInfo):
        service = 'pinpoint-sms-voice-v2'
        permission_prefix = 'sms-voice'
        enum_spec = ('describe_configuration_sets', 'ConfigurationSets', None)
        id = name = 'ConfigurationSetName'
        arn = 'ConfigurationSetArn'
        date = 'CreatedTimestamp'
        cfn_type = 'AWS::SMSVOICE::ConfigurationSet'
        universal_taggable = object()

    source_mapping = {'describe': DescribeWithResourceTags}


class SmsVoiceCrossAccount(CrossAccountAccessFilter):
    """Filter resources whose resource-based policy grants access to
    principals outside the allowed accounts or organizations.

    Only phone numbers, sender ids, pools and opt-out lists support
    resource-based policies.

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-phone-number-cross-account
            resource: aws.sms-voice-phone-number
            filters:
              - type: cross-account
                whitelist_orgids:
                  - o-xxxxxxxxxx
    """

    policy_attribute = 'c7n:Policy'
    permissions = ('sms-voice:GetResourcePolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client(
            self.manager.resource_type.service)
        arn_key = self.manager.resource_type.arn
        for r in resources:
            if self.policy_attribute in r:
                continue
            try:
                r[self.policy_attribute] = self.manager.retry(
                    client.get_resource_policy, ResourceArn=r[arn_key]).get('Policy')
            except client.exceptions.ResourceNotFoundException:
                r[self.policy_attribute] = None
        return super().process(resources, event)


for resource_class in (SmsVoicePhoneNumber, SmsVoiceSenderId, SmsVoicePool):
    resource_class.filter_registry.register('cross-account', SmsVoiceCrossAccount)
