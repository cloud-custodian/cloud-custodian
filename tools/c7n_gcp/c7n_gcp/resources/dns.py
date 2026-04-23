# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.actions import MethodAction
from c7n.utils import type_schema, local_session
from c7n.filters.core import ListItemFilter
from c7n.exceptions import PolicyValidationError


@resources.register('dns-managed-zone')
class DnsManagedZone(QueryResourceManager):
    """GCP resource: https://cloud.google.com/dns/docs/reference/v1beta2/managedZones
    """
    class resource_type(TypeInfo):
        service = 'dns'
        version = 'v1beta2'
        component = 'managedZones'
        enum_spec = ('list', 'managedZones[]', None)
        scope = 'project'
        id = 'id'
        name = 'name'
        default_report_fields = ['id', 'name', 'dnsName', 'creationTime', 'visibility']
        asset_type = "dns.googleapis.com/ManagedZone"
        scc_type = "google.cloud.dns.ManagedZone"
        urn_component = "managed-zone"
        urn_id_path = "name"

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'project': resource_info['project_id'],
                        'managedZone': resource_info['zone_name']})


@resources.register('dns-policy')
class DnsPolicy(QueryResourceManager):
    """GCP resource: https://cloud.google.com/dns/docs/reference/v1beta2/policies
    """
    class resource_type(TypeInfo):
        service = 'dns'
        version = 'v1beta2'
        component = 'policies'
        enum_spec = ('list', 'policies[]', None)
        scope = 'project'
        id = 'id'
        name = 'name'
        default_report_fields = ['id', 'name', 'description', 'enableLogging']
        asset_type = "dns.googleapis.com/Policy"
        urn_component = "policy"
        urn_id_path = "name"

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'project': resource_info['project_id'],
                        'policy': resource_info['policy_name']})


@DnsPolicy.action_registry.register('update')
class UpdatePolicy(MethodAction):
    """Update DNS policy settings.

    :example:

    .. code-block:: yaml

            policies:
              - name: gcp-dns-policy-enable-logging
                resource: gcp.dns-policy
                filters:
                  - type: value
                    key: enableLogging
                    value: false
                actions:
                  - type: update
                    enableLogging: true
    """

    schema = type_schema(
        'update',
        **{
            'description': {'type': 'string'},
            'enableInboundForwarding': {'type': 'boolean'},
            'enableLogging': {'type': 'boolean'},
            'alternativeNameServerConfig': {'type': 'object'},
            'networks': {'type': 'array', 'items': {'type': 'object'}}
        }
    )
    method_spec = {'op': 'patch'}
    # `update` is the permission name; there is no `dns.policies.patch` IAM permission.
    method_perm = 'update'
    update_fields = (
        'description',
        'enableInboundForwarding',
        'enableLogging',
        'alternativeNameServerConfig',
        'networks',
    )

    def get_resource_params(self, model, resource):
        project = local_session(self.manager.source.query.session_factory).get_default_project()
        body = {}
        for field in self.update_fields:
            if field in self.data:
                body[field] = self.data[field]

        return {'project': project, 'policy': resource['name'], 'body': body}

    def validate(self):
        super().validate()
        if not any(field in self.data for field in self.update_fields):
            raise PolicyValidationError(
                "policy:{} action:{} requires at least one mutable policy field".format(
                    self.manager.ctx.policy.name, self.type
                )
            )
        return self


@DnsManagedZone.filter_registry.register('records-sets')
class DNSZoneRecordsSetsFilter(ListItemFilter):

    schema = type_schema(
        'records-sets',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'}
    )
    annotate_items = True
    permissions = ("dns.managedZones.list",)

    def get_item_values(self, resource):
        session = local_session(self.manager.session_factory)
        client = session.client(service_name='dns', version='v1', component='resourceRecordSets')
        project = session.get_default_project()
        result = client.execute_query(
            'list', {'project': project, 'managedZone': resource['name']}).get('rrsets')
        return result


@DnsManagedZone.action_registry.register('delete')
class Delete(MethodAction):
    """Action to delete DNS managed zones

    It is recommended to use a filter to avoid unwanted deletion of DNS managed zones

    :example:

    .. code-block:: yaml

            policies:
              - name: gcp-delete-testing-dns-managed-zones
                resource: gcp.dns-managed-zone
                filters:
                  - type: value
                    key: name
                    op: eq
                    value: 'test-custodian.com'
                actions:
                  - type: delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, model, resource):
        project = local_session(self.manager.source.query.session_factory).get_default_project()
        return {
            'project': project,
            'managedZone': resource['name']}
