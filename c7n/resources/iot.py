# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.filters import Filter
from c7n.filters.policystatement import HasStatementFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, RetryPageIterator, TypeInfo
from c7n.utils import local_session, type_schema


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
        universal_taggable = object()


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
        universal_taggable = object()

    permissions = ('iot:ListPolicies', 'iot:GetPolicy')


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
                client.delete_policy(policyName=r['policyName'])
            except client.exceptions.ResourceNotFoundException:
                continue
            except client.exceptions.DeleteConflictException as e:
                self.log.warning(
                    'policy:%s could not be deleted: %s', r['policyName'], e)

    def _detach(self, client, r, force):
        targets = r.get(IoTPolicyAttached.annotation_key)
        if targets is None:
            pager = client.get_paginator('list_targets_for_policy')
            pager.PAGE_ITERATOR_CLS = RetryPageIterator
            targets = pager.paginate(
                policyName=r['policyName']).build_full_result().get('targets', [])
        if targets and not force:
            self.log.warning(
                'policy:%s skipped, attached to %d target(s)',
                r['policyName'], len(targets))
            return False
        for t in targets:
            client.detach_policy(policyName=r['policyName'], target=t)
        return True

    def _delete_versions(self, client, r):
        for v in client.list_policy_versions(
                policyName=r['policyName']).get('policyVersions', []):
            if v['isDefaultVersion']:
                continue
            client.delete_policy_version(
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
        date = 'creationDate'
        cfn_type = 'AWS::IoT::Certificate'

    permissions = ('iot:ListCertificates', 'iot:DescribeCertificate')


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
            client.update_certificate(
                certificateId=r['certificateId'], newStatus='INACTIVE')


@resources.register('iot-ota-update')
class IoTOTAUpdate(QueryResourceManager):
    """AWS IoT Over-the-Air (OTA) firmware / component update."""

    class resource_type(TypeInfo):
        service = 'iot'
        enum_spec = ('list_ota_updates', 'otaUpdates', None)
        detail_spec = (
            'get_ota_update', 'otaUpdateId', 'otaUpdateId', 'otaUpdateInfo')
        id = 'otaUpdateId'
        name = 'otaUpdateId'
        arn = 'otaUpdateArn'
        date = 'creationDate'
        cfn_type = 'AWS::IoT::OTAUpdate'
        universal_taggable = object()

    permissions = ('iot:ListOTAUpdates', 'iot:GetOTAUpdate')


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
        files = r.get('otaUpdateFiles') or []
        if not files:
            return True
        for f in files:
            signing = f.get('codeSigning') or {}
            signed = (
                signing.get('awsSignerJobId')
                or signing.get('startSigningJobParameter')
                or signing.get('customCodeSigning'))
            if not signed:
                return True
        return False
