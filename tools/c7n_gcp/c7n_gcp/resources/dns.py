# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.actions import MethodAction
from c7n.utils import type_schema, local_session, jmespath_search
from c7n.filters import ValueFilter
from c7n.filters.core import OPERATORS


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


@DnsManagedZone.filter_registry.register('records-sets')
class DNSZoneRecordsSetsFilter(ValueFilter):
    schema = type_schema('records-sets', rinherit=ValueFilter.schema)
    permissions = ("dns.managedZones.list",)

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)
        client = session.client(service_name='dns', version='v1', component='resourceRecordSets')
        result = []
        op = OPERATORS[self.data.get('op')]
        project = session.get_default_project()

        for resource in resources:
            sets = client.execute_query('list', {'project': project,
                                                 'managedZone': resource['name']})
            for s in sets['rrsets']:
                jmespath_key = jmespath_search(self.data.get('key'), s)
                if jmespath_key and op(jmespath_key, self.data.get('value')):
                    result.append(resource)
                    break

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
