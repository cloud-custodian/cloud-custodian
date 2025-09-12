# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Security Command Center Findings suppport for GCP resources
"""
from c7n.filters.core import ValueFilter
from c7n.utils import local_session, type_schema
from c7n_gcp.provider import resources as gcp_resources


class SecurityComandCenterFindingsFilter(ValueFilter):
    """Filters resources based on their Security Command Center (SCC) findings.

    .. code-block:: yaml

      - name: bucket-contains-high-finding
        resource: gcp.bucket
        filters:
        - type: scc-findings
          org: 11111111111111
          key: severity
          value: HIGH
    """

    schema = type_schema('scc-findings', rinherit=ValueFilter.schema,
    org={'type': 'integer'}, required=['org'])
    required_keys = {}
    permissions = ("securitycenter.findings.list",)
    annotation_key = 'c7n:matched-findings'

    def process(self, resources, event=None):
        if not resources[0].get(self.annotation_key):
            findings_list = self.get_findings(resources)
            self.split_by_resource(findings_list)
        matched = [r for r in resources if self.process_resource(r)]
        return matched

    def get_findings(self, resources):
        self.findings_by_resource = {}
        query_params = {
            'filter': self.get_resource_filter(resources),
            'pageSize': 1000
        }
        session = local_session(self.manager.session_factory)
        client = session.client("securitycenter", "v1", "organizations.sources.findings")
        findings_paged_list = list(client.execute_paged_query('list',
            {'parent': 'organizations/{}/sources/-'.format(self.data['org']), **query_params}))
        findings_list = []
        for findings_page in findings_paged_list:
            if findings_page.get('listFindingsResults'):
                findings_list.extend(findings_page['listFindingsResults'])
        return findings_list

    def get_resource_filter(self, resources):
        resource_filter = []
        for r in resources:
            resource_filter.append('resourceName:"{}"'.format(r[self.manager.resource_type.name]))
            resource_filter.append(' OR ')
        resource_filter.pop()

        return ''.join(resource_filter)

    def split_by_resource(self, finding_list):
        for f in finding_list:
            resource_name = f["finding"]["resourceName"].split('/')[-1]
            resource_findings = self.findings_by_resource.get(resource_name, [])
            resource_findings.append(f['finding'])
            self.findings_by_resource[resource_name] = resource_findings

    def process_resource(self, resource):
        if not resource.get(self.annotation_key):
            resource_name = resource[self.manager.resource_type.name]
            resource[self.annotation_key] = self.findings_by_resource.get(resource_name, [])

        if self.data.get('key'):
            resource[self.annotation_key] = [
                finding for finding in resource[self.annotation_key] if self.match(finding)]
        return len(resource[self.annotation_key]) > 0

    @classmethod
    def register_resources(klass, registry, resource_class):
        if resource_class.filter_registry:
            resource_class.filter_registry.register('scc-findings', klass)


gcp_resources.subscribe(SecurityComandCenterFindingsFilter.register_resources)
