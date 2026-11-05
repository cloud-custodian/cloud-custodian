# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters import CrossAccountAccessFilter, ValueFilter
from c7n.filters.related import RelatedResourceFilter
from c7n.manager import resources
from c7n.query import DescribeSource, QueryResourceManager, TypeInfo
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema


class DescribeSmsVoice(DescribeSource):
    """Describe source that adds tags via the service's ListTagsForResource."""

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client(
            self.manager.resource_type.service)
        arn_key = self.manager.resource_type.arn
        for r in resources:
            r['Tags'] = self.manager.retry(
                client.list_tags_for_resource, ResourceArn=r[arn_key]).get('Tags', [])
        return resources


class SmsVoiceTypeInfo(TypeInfo):
    service = 'pinpoint-sms-voice-v2'
    permission_prefix = 'sms-voice'
    permissions_augment = ('sms-voice:ListTagsForResource',)


class SmsVoiceResourceManager(QueryResourceManager):
    source_mapping = {'describe': DescribeSmsVoice}


@resources.register('sms-voice-phone-number')
class SmsVoicePhoneNumber(SmsVoiceResourceManager):
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

    class resource_type(SmsVoiceTypeInfo):
        # Owner=SELF excludes phone numbers shared into the account by others
        enum_spec = ('describe_phone_numbers', 'PhoneNumbers', {'Owner': 'SELF'})
        id = 'PhoneNumberId'
        name = 'PhoneNumber'
        arn = 'PhoneNumberArn'
        arn_type = 'phone-number'
        date = 'CreatedTimestamp'
        cfn_type = 'AWS::SMSVOICE::PhoneNumber'


@resources.register('sms-voice-sender-id')
class SmsVoiceSenderId(SmsVoiceResourceManager):
    """AWS End User Messaging SMS - Sender ID

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-sender-id-unregistered
            resource: aws.sms-voice-sender-id
            filters:
              - Registered: false
    """

    class resource_type(SmsVoiceTypeInfo):
        enum_spec = ('describe_sender_ids', 'SenderIds', {'Owner': 'SELF'})
        # a sender id is only unique per country, so key on the arn
        id = arn = 'SenderIdArn'
        name = 'SenderId'
        arn_type = 'sender-id'
        cfn_type = 'AWS::SMSVOICE::SenderId'


@resources.register('sms-voice-pool')
class SmsVoicePool(SmsVoiceResourceManager):
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

    class resource_type(SmsVoiceTypeInfo):
        enum_spec = ('describe_pools', 'Pools', {'Owner': 'SELF'})
        id = name = 'PoolId'
        arn = 'PoolArn'
        arn_type = 'pool'
        date = 'CreatedTimestamp'
        cfn_type = 'AWS::SMSVOICE::Pool'


@resources.register('sms-voice-configuration-set')
class SmsVoiceConfigurationSet(SmsVoiceResourceManager):
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

    class resource_type(SmsVoiceTypeInfo):
        enum_spec = ('describe_configuration_sets', 'ConfigurationSets', None)
        id = name = 'ConfigurationSetName'
        arn = 'ConfigurationSetArn'
        arn_type = 'configuration-set'
        date = 'CreatedTimestamp'
        cfn_type = 'AWS::SMSVOICE::ConfigurationSet'


@resources.register('sms-voice-registration')
class SmsVoiceRegistration(SmsVoiceResourceManager):
    """AWS End User Messaging SMS - Registration

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-registration-requires-updates
            resource: aws.sms-voice-registration
            filters:
              - RegistrationStatus: REQUIRES_UPDATES
    """

    class resource_type(SmsVoiceTypeInfo):
        enum_spec = ('describe_registrations', 'Registrations', None)
        id = name = 'RegistrationId'
        arn = 'RegistrationArn'
        arn_type = 'registration'
        date = 'CreatedTimestamp'


class SmsVoiceTag(Tag):
    """Create tags on End User Messaging SMS resources

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-phone-number-tag
            resource: aws.sms-voice-phone-number
            filters:
              - tag:Owner: absent
            actions:
              - type: tag
                key: Owner
                value: unknown
    """

    permissions = ('sms-voice:TagResource',)

    def process_resource_set(self, client, resource_set, tags):
        arn_key = self.manager.resource_type.arn
        for r in resource_set:
            self.manager.retry(client.tag_resource, ResourceArn=r[arn_key], Tags=tags)


class SmsVoiceRemoveTag(RemoveTag):
    """Remove tags from End User Messaging SMS resources

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-phone-number-remove-tag
            resource: aws.sms-voice-phone-number
            filters:
              - tag:Stale: present
            actions:
              - type: remove-tag
                tags: [Stale]
    """

    permissions = ('sms-voice:UntagResource',)

    def process_resource_set(self, client, resource_set, tag_keys):
        arn_key = self.manager.resource_type.arn
        for r in resource_set:
            self.manager.retry(client.untag_resource, ResourceArn=r[arn_key], TagKeys=tag_keys)


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


class SmsVoiceRegistrationFilter(RelatedResourceFilter):
    """Filter origination identities by their associated registration.

    Identities without a registration have nothing to match, so wrap the
    filter in ``not`` to also catch unregistered identities.

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-phone-number-registration-incomplete
            resource: aws.sms-voice-phone-number
            filters:
              - not:
                - type: registration
                  key: RegistrationStatus
                  value: COMPLETE
    """

    schema = type_schema('registration', rinherit=ValueFilter.schema)
    RelatedResource = 'c7n.resources.smsvoice.SmsVoiceRegistration'
    RelatedIdsExpression = 'RegistrationId'
    AnnotationKey = 'Registrations'


class SmsVoicePhoneNumberPoolFilter(RelatedResourceFilter):
    """Filter phone numbers by attributes (including tags) of their pool.

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-prod-pool-phone-number-registration
            resource: aws.sms-voice-phone-number
            filters:
              - type: pool
                key: tag:Environment
                value: prod
              - not:
                - type: registration
                  key: RegistrationStatus
                  value: COMPLETE
    """

    schema = type_schema(
        'pool', rinherit=ValueFilter.schema, operator={'enum': ['and', 'or']})
    RelatedResource = 'c7n.resources.smsvoice.SmsVoicePool'
    RelatedIdsExpression = 'PoolId'
    AnnotationKey = 'PoolIds'


class SmsVoiceSenderIdPoolFilter(SmsVoicePhoneNumberPoolFilter):
    """Filter sender ids by attributes (including tags) of the pools they belong to.

    Sender ids don't reference their pools, so membership is resolved
    from each pool's origination identities.

    :example:

    .. code-block:: yaml

        policies:
          - name: sms-voice-prod-pool-sender-id-registration
            resource: aws.sms-voice-sender-id
            filters:
              - type: pool
                key: tag:Environment
                value: prod
              - not:
                - type: registration
                  key: RegistrationStatus
                  value: COMPLETE
    """

    membership_key = 'c7n:PoolMembership'
    RelatedIdsExpression = '"c7n:PoolMembership"[]'

    def get_permissions(self):
        return list(super().get_permissions()) + ['sms-voice:ListPoolOriginationIdentities']

    def get_related(self, resources):
        pools = {p['PoolId']: p for p in self.get_resource_manager().resources()}
        client = local_session(self.manager.session_factory).client(
            self.manager.resource_type.service)
        paginator = client.get_paginator('list_pool_origination_identities')
        membership = {}
        for pool_id in pools:
            for page in paginator.paginate(PoolId=pool_id):
                for identity in page.get('OriginationIdentities', []):
                    membership.setdefault(
                        identity['OriginationIdentityArn'], set()).add(pool_id)
        for r in resources:
            r[self.membership_key] = sorted(membership.get(r['SenderIdArn'], ()))
        return pools


for resource_class in (
        SmsVoicePhoneNumber, SmsVoiceSenderId, SmsVoicePool,
        SmsVoiceConfigurationSet, SmsVoiceRegistration):
    resource_class.action_registry.register('tag', SmsVoiceTag)
    resource_class.action_registry.register('remove-tag', SmsVoiceRemoveTag)
    resource_class.action_registry.register('mark-for-op', TagDelayedAction)
    resource_class.filter_registry.register('marked-for-op', TagActionFilter)

for resource_class in (SmsVoicePhoneNumber, SmsVoiceSenderId, SmsVoicePool):
    resource_class.filter_registry.register('cross-account', SmsVoiceCrossAccount)

for resource_class in (SmsVoicePhoneNumber, SmsVoiceSenderId):
    resource_class.filter_registry.register('registration', SmsVoiceRegistrationFilter)

SmsVoicePhoneNumber.filter_registry.register('pool', SmsVoicePhoneNumberPoolFilter)
SmsVoiceSenderId.filter_registry.register('pool', SmsVoiceSenderIdPoolFilter)
