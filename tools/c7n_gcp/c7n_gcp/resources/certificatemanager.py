# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.utils import type_schema

from c7n_gcp.actions import MethodAction
from c7n_gcp.actions.labels import SetLabelsAction, LabelDelayedAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('certmanager-certificate')
class CertificateManagerCertificate(QueryResourceManager):
    """GCP Certificate Manager Certificate

    https://cloud.google.com/certificate-manager/docs/reference/certificate-manager/rest/v1/projects.locations.certificates
    """

    class resource_type(TypeInfo):
        service = 'certificatemanager'
        version = 'v1'
        component = 'projects.locations.certificates'
        enum_spec = ('list', 'certificates[]', None)
        scope = 'project'
        scope_template = 'projects/{}/locations/-'
        scope_key = 'parent'
        name = 'name'
        id = 'name'
        labels = False  # Disable automatic label registration
        labels_op = 'patch'
        default_report_fields = [
            'name', 'description', 'createTime', 'expireTime',
            'updateTime', 'labels', 'sanDnsnames', 'usedBy'
        ]
        asset_type = 'certificatemanager.googleapis.com/Certificate'
        urn_component = 'certificate'
        urn_id_segments = (-1,)  # Extract certificate name from full path
        permissions = (
            'certificatemanager.certs.list',
            'certificatemanager.certs.get',
            'certificatemanager.certs.update'
        )

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': resource_info['name']})

        @staticmethod
        def get_label_params(resource, all_labels):
            return {
                'name': resource['name'],
                'body': {
                    'labels': all_labels
                },
                'updateMask': 'labels'
            }

        @classmethod
        def refresh(cls, client, resource):
            return cls.get(client, {'name': resource['name']})


@CertificateManagerCertificate.action_registry.register('delete')
class DeleteCertificate(MethodAction):
    """Delete Certificate Manager Certificate

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-unused-certificates
            resource: gcp.certmanager-certificate
            filters:
              - type: value
                key: labels.environment
                value: staging
            actions:
              - type: delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ('certificatemanager.certs.delete',)

    def get_resource_params(self, model, resource):
        return {'name': resource['name']}


@CertificateManagerCertificate.action_registry.register('set-labels')
class CertificateSetLabelsAction(SetLabelsAction):
    """Set labels to Certificate Manager Certificate

    :example:

    .. code-block:: yaml

        policies:
          - name: label-certificates
            resource: gcp.certmanager-certificate
            actions:
              - type: set-labels
                labels:
                  environment: test
    """

    permissions = ('certificatemanager.certs.update',)

    def get_permissions(self):
        return self.permissions


@CertificateManagerCertificate.action_registry.register('mark-for-op')
class CertificateMarkForOpAction(LabelDelayedAction):
    """Mark Certificate Manager Certificate for future action

    :example:

    .. code-block:: yaml

        policies:
          - name: mark-certificates-for-deletion
            resource: gcp.certmanager-certificate
            actions:
              - type: mark-for-op
                op: delete
                days: 7
    """

    permissions = ('certificatemanager.certs.update',)

    def get_permissions(self):
        return self.permissions


@resources.register('certmanager-certificate-map')
class CertificateManagerMap(QueryResourceManager):
    """GCP Certificate Manager Certificate Map

    https://cloud.google.com/certificate-manager/docs/reference/certificate-manager/rest/v1/projects.locations.certificateMaps
    """

    class resource_type(TypeInfo):
        service = 'certificatemanager'
        version = 'v1'
        component = 'projects.locations.certificateMaps'
        enum_spec = ('list', 'certificateMaps[]', None)
        scope = 'project'
        scope_template = 'projects/{}/locations/-'
        scope_key = 'parent'
        name = 'name'
        id = 'name'
        labels = True
        labels_op = 'patch'
        default_report_fields = [
            'name', 'description', 'createTime', 'updateTime',
            'labels', 'gclbTargets'
        ]
        asset_type = 'certificatemanager.googleapis.com/CertificateMap'
        urn_component = 'certificate-map'
        urn_id_segments = (-1,)  # Extract certificate map name from full path
        permissions = (
            'certificatemanager.certmaps.list',
            'certificatemanager.certmaps.get',
            'certificatemanager.certmaps.update'
        )

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': resource_info['name']})

        @staticmethod
        def get_label_params(resource, all_labels):
            return {
                'name': resource['name'],
                'body': {
                    'labels': all_labels
                },
                'updateMask': 'labels'
            }

        @classmethod
        def refresh(cls, client, resource):
            return cls.get(client, {'name': resource['name']})


@CertificateManagerMap.action_registry.register('delete')
class DeleteCertificateMap(MethodAction):
    """Delete Certificate Manager Certificate Map

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-unused-certificate-maps
            resource: gcp.certmanager-certificate-map
            filters:
              - type: value
                key: labels.environment
                value: staging
            actions:
              - type: delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ('certificatemanager.certmaps.delete',)

    def get_resource_params(self, model, resource):
        return {'name': resource['name']}


@CertificateManagerMap.action_registry.register('set-labels')
class CertificateMapSetLabelsAction(SetLabelsAction):
    """Set labels to Certificate Manager Certificate Map

    :example:

    .. code-block:: yaml

        policies:
          - name: label-certificate-maps
            resource: gcp.certmanager-certificate-map
            actions:
              - type: set-labels
                labels:
                  environment: production
    """

    permissions = ('certificatemanager.certmaps.update',)

    def get_permissions(self):
        return self.permissions


@CertificateManagerMap.action_registry.register('mark-for-op')
class CertificateMapMarkForOpAction(LabelDelayedAction):
    """Mark Certificate Manager Certificate Map for future action

    :example:

    .. code-block:: yaml

        policies:
          - name: mark-certificate-maps-for-deletion
            resource: gcp.certmanager-certificate-map
            actions:
              - type: mark-for-op
                op: delete
                days: 7
    """

    permissions = ('certificatemanager.certmaps.update',)

    def get_permissions(self):
        return self.permissions
