# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

from c7n.actions import Action
from c7n.filters import Filter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.resources.account import Account
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
    """AWS IoT authorization (device) policy.

    The ``policyDocument`` is fetched per-policy via ``get_policy`` so that
    filters can inspect the granted actions/resources.
    """

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


@IoTPolicy.filter_registry.register('no-wildcard')
class IoTPolicyNoWildcard(Filter):
    """Select IoT policies whose document contains a wildcard.

    Matches an ``Allow`` statement that grants ``iot:*`` / ``*`` actions
    or a ``*`` resource. IoT policy documents use IoT topic / client ARNs
    (they are not IAM resource policies), so this parses the document
    directly rather than using CrossAccountAccessFilter.

    :example:

    .. code-block:: yaml

        policies:
          - name: iot-policy-wildcard
            resource: aws.iot-policy
            filters:
              - type: no-wildcard
    """

    schema = type_schema('no-wildcard')
    permissions = ('iot:GetPolicy',)

    def process(self, resources, event=None):
        return [r for r in resources if self._has_wildcard(r)]

    def _has_wildcard(self, r):
        doc = r.get('policyDocument')
        if not doc:
            return False
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except (ValueError, TypeError):
                return False
        statements = doc.get('Statement', [])
        if isinstance(statements, dict):
            statements = [statements]
        for stmt in statements:
            if stmt.get('Effect') != 'Allow':
                continue
            actions = stmt.get('Action', [])
            actions = [actions] if isinstance(actions, str) else actions
            resources_ = stmt.get('Resource', [])
            resources_ = [resources_] if isinstance(resources_, str) else resources_
            if any(a == '*' or a == 'iot:*' or a.endswith(':*') for a in actions):
                return True
            if '*' in resources_:
                return True
        return False


@resources.register('iot-authorizer')
class IoTAuthorizer(QueryResourceManager):
    """AWS IoT custom authorizer."""

    class resource_type(TypeInfo):
        service = 'iot'
        enum_spec = ('list_authorizers', 'authorizers', None)
        detail_spec = (
            'describe_authorizer', 'authorizerName',
            'authorizerName', 'authorizerDescription')
        id = 'authorizerName'
        name = 'authorizerName'
        arn = 'authorizerArn'
        cfn_type = 'AWS::IoT::Authorizer'
        universal_taggable = object()

    permissions = ('iot:ListAuthorizers', 'iot:DescribeAuthorizer')


@resources.register('iot-certificate')
class IoTCertificate(QueryResourceManager):
    """AWS IoT device X.509 certificate.

    ``describe_certificate`` enriches each certificate with ``validity``
    (notBefore/notAfter) and ``caCertificateId``. Certificate age is
    expressed with a ``value`` filter on ``creationDate`` (value_type:
    age); ``set-inactive`` provides the corrective step.
    """

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
        # IoT certificates are NOT taggable in AWS - no universal_taggable.

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
    """Select OTA updates that include any unsigned file.

    A file is signed when it carries a ``codeSigning`` block referencing
    an AWS Signer job (``awsSignerJobId`` / ``startSigningJobParameter``)
    or a ``customCodeSigning`` signature.

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
            # No file detail available; treat as non-compliant so it is
            # surfaced for review rather than silently passing.
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


@Account.filter_registry.register('iot-logging')
class IoTLoggingEnabled(Filter):
    """Check account-level IoT (V2) logging configuration.

    IoT device activity logging's only destination is CloudWatch Logs, so
    "enabled and sent to CloudWatch" is satisfied when logging is not
    disabled, a role is attached, and the default log level is not
    ``DISABLED``. Returns the account resource when logging is
    non-compliant.

    :example:

    .. code-block:: yaml

        policies:
          - name: iot-logging-disabled
            resource: account
            filters:
              - type: iot-logging
    """

    schema = type_schema('iot-logging')
    permissions = ('iot:GetV2LoggingOptions',)
    annotation_key = 'c7n:iot-logging'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('iot')
        options = client.get_v2_logging_options()
        options.pop('ResponseMetadata', None)
        compliant = (
            not options.get('disableAllLogs', False)
            and bool(options.get('roleArn'))
            and options.get('defaultLogLevel') not in (None, 'DISABLED'))
        if compliant:
            return []
        resources[0][self.annotation_key] = options
        return resources
