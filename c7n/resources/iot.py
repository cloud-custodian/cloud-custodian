# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.filters import Filter
from c7n.filters.policystatement import HasStatementFilter
from c7n.manager import resources
from c7n.query import (
    DescribeSource, QueryResourceManager, RetryPageIterator, TypeInfo)
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import get_retry, local_session, type_schema


RETRY = get_retry((
    'ThrottlingException',
    'ServiceUnavailableException',
    'InternalFailureException',
))


class TagIoTResource(Tag):

    permissions = ('iot:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        arn_key = self.manager.resource_type.arn
        for r in resources:
            try:
                self.manager.retry(
                    client.tag_resource, resourceArn=r[arn_key], tags=new_tags)
            except client.exceptions.ResourceNotFoundException:
                continue


class RemoveTagIoTResource(RemoveTag):

    permissions = ('iot:UntagResource',)

    def process_resource_set(self, client, resources, tag_keys):
        arn_key = self.manager.resource_type.arn
        for r in resources:
            try:
                self.manager.retry(
                    client.untag_resource,
                    resourceArn=r[arn_key], tagKeys=tag_keys)
            except client.exceptions.ResourceNotFoundException:
                continue


def register_iot_tagging(klass):
    klass.action_registry.register('tag', TagIoTResource)
    klass.action_registry.register('remove-tag', RemoveTagIoTResource)
    klass.action_registry.register('mark-for-op', TagDelayedAction)
    klass.filter_registry.register('marked-for-op', TagActionFilter)
    return klass


class DescribeIoTResource(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        client = local_session(self.manager.session_factory).client('iot')
        arn_key = self.manager.resource_type.arn
        for r in resources:
            r['Tags'] = self.manager.retry(
                client.list_tags_for_resource,
                resourceArn=r[arn_key]).get('tags', [])
        return resources


@resources.register('iot')
class IoT(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'iot'
        enum_spec = ('list_things', 'things', None)
        name = "thingName"
        id = "thingName"
        arn = "thingArn"
        default_report_fields = (
            'thingName',
            'thingTypeName'
        )
        cfn_type = 'AWS::IoT::Thing'

    retry = staticmethod(RETRY)


@register_iot_tagging
@resources.register('iot-policy')
class IoTPolicy(QueryResourceManager):
    """AWS IoT policy."""

    class resource_type(TypeInfo):
        service = 'iot'
        enum_spec = ('list_policies', 'policies', None)
        detail_spec = ('get_policy', 'policyName', 'policyName', None)
        id = 'policyName'
        name = 'policyName'
        arn = 'policyArn'
        cfn_type = 'AWS::IoT::Policy'
        permissions_augment = ('iot:ListTagsForResource',)

    source_mapping = {'describe': DescribeIoTResource}
    retry = staticmethod(RETRY)


@IoTPolicy.filter_registry.register('attached')
class IoTPolicyAttached(Filter):
    """Filter IoT policies by whether they are attached to any target.

    :example:

    .. code-block:: yaml

        policies:
          - name: iot-policy-orphaned
            resource: aws.iot-policy
            filters:
              - type: attached
                state: false
    """

    schema = type_schema('attached', state={'type': 'boolean'})
    permissions = ('iot:ListTargetsForPolicy',)
    annotation_key = 'c7n:Targets'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('iot')
        pager = client.get_paginator('list_targets_for_policy')
        pager.PAGE_ITERATOR_CLS = RetryPageIterator
        for r in resources:
            r[self.annotation_key] = pager.paginate(
                policyName=r['policyName']).build_full_result().get('targets', [])
        state = self.data.get('state', True)
        return [r for r in resources
                if bool(r[self.annotation_key]) == state]


@IoTPolicy.filter_registry.register('has-statement')
class IoTPolicyHasStatement(HasStatementFilter):

    policy_attribute = 'policyDocument'

    def get_std_format_args(self, policy):
        return {
            'policy_arn': policy['policyArn'],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region,
        }


@IoTPolicy.action_registry.register('delete')
class DeleteIoTPolicy(Action):
    """Delete an IoT policy.

    Non-default versions are deleted and targets detached first, as required
    by the API. Set ``force`` to detach targets; without it an attached policy
    is skipped.

    :example:

    .. code-block:: yaml

        policies:
          - name: iot-policy-delete-orphaned
            resource: aws.iot-policy
            filters:
              - type: attached
                state: false
            actions:
              - delete
    """

    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = (
        'iot:DeletePolicy', 'iot:DeletePolicyVersion',
        'iot:ListPolicyVersions', 'iot:ListTargetsForPolicy',
        'iot:DetachPolicy')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iot')
        force = self.data.get('force', False)
        for r in resources:
            try:
                if not self._detach(client, r, force):
                    continue
                self._delete_versions(client, r)
                self.manager.retry(
                    client.delete_policy, policyName=r['policyName'])
            except client.exceptions.ResourceNotFoundException:
                continue
            except client.exceptions.DeleteConflictException as e:
                self.log.warning(
                    'policy:%s could not be deleted, it may take up to five '
                    'minutes after detachment before deletion succeeds: %s',
                    r['policyName'], e)

    def _detach(self, client, r, force):
        targets = r.get(IoTPolicyAttached.annotation_key)
        if targets is None:
            pager = client.get_paginator('list_targets_for_policy')
            pager.PAGE_ITERATOR_CLS = RetryPageIterator
            targets = pager.paginate(
                policyName=r['policyName']).build_full_result().get('targets', [])
        if targets and not force:
            self.log.warning(
                'policy:%s detachment skipped, attached to %d target(s).  '
                'Use "force" flag to detach.',
                r['policyName'], len(targets))
            return False
        for t in targets:
            self.manager.retry(
                client.detach_policy, policyName=r['policyName'], target=t)
        return True

    def _delete_versions(self, client, r):
        versions = self.manager.retry(
            client.list_policy_versions, policyName=r['policyName'])
        for v in versions.get('policyVersions', []):
            if v['isDefaultVersion']:
                continue
            self.manager.retry(
                client.delete_policy_version,
                policyName=r['policyName'], policyVersionId=v['versionId'])


@resources.register('iot-certificate')
class IoTCertificate(QueryResourceManager):
    """AWS IoT device X.509 certificate."""

    class resource_type(TypeInfo):
        service = 'iot'
        enum_spec = ('list_certificates', 'certificates', None)
        detail_spec = (
            'describe_certificate', 'certificateId',
            'certificateId', 'certificateDescription')
        id = 'certificateId'
        name = 'certificateId'
        arn = 'certificateArn'
        date = 'lastModifiedDate'
        cfn_type = 'AWS::IoT::Certificate'

    retry = staticmethod(RETRY)


@IoTCertificate.action_registry.register('set-inactive')
class SetCertificateInactive(Action):
    """Deactivate an IoT device certificate.

    :example:

    .. code-block:: yaml

        policies:
          - name: iot-cert-rotate-12-months
            resource: aws.iot-certificate
            filters:
              - type: value
                key: status
                value: ACTIVE
              - type: value
                key: creationDate
                value_type: age
                op: greater-than
                value: 365
            actions:
              - set-inactive
    """

    schema = type_schema('set-inactive')
    permissions = ('iot:UpdateCertificate',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iot')
        for r in resources:
            self.manager.retry(
                client.update_certificate,
                certificateId=r['certificateId'], newStatus='INACTIVE')


@register_iot_tagging
@resources.register('iot-ota-update')
class IoTOTAUpdate(QueryResourceManager):
    """AWS IoT Over-the-Air (OTA) update."""

    class resource_type(TypeInfo):
        service = 'iot'
        enum_spec = ('list_ota_updates', 'otaUpdates', None)
        detail_spec = (
            'get_ota_update', 'otaUpdateId', 'otaUpdateId', 'otaUpdateInfo')
        id = 'otaUpdateId'
        name = 'otaUpdateId'
        arn = 'otaUpdateArn'
        date = 'lastModifiedDate'
        cfn_type = 'AWS::IoT::OTAUpdate'
        permissions_enum = ('iot:ListOTAUpdates')
        permissions_augment = ('iot:ListTagsForResource', 'iot:getOTAUpdate')

    source_mapping = {'describe': DescribeIoTResource}
    retry = staticmethod(RETRY)


@IoTOTAUpdate.filter_registry.register('unsigned')
class IoTOTAUpdateUnsigned(Filter):
    """Select OTA updates that include an unsigned file.

    :example:

    .. code-block:: yaml

        policies:
          - name: iot-ota-unsigned
            resource: aws.iot-ota-update
            filters:
              - type: unsigned
    """

    schema = type_schema('unsigned')
    permissions = ('iot:GetOTAUpdate',)

    def process(self, resources, event=None):
        return [r for r in resources if self._has_unsigned_file(r)]

    def _has_unsigned_file(self, r):
        for f in r.get('otaUpdateFiles', []):
            signing = f.get('codeSigning', {})
            signed = (
                signing.get('awsSignerJobId')
                or signing.get('startSigningJobParameter')
                or signing.get('customCodeSigning'))
            if not signed:
                return True
        return False
