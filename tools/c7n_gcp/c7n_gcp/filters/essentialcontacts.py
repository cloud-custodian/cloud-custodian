# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Essential Contacts suppport for GCP organization
"""
from c7n.filters.core import ValueFilter
from c7n.utils import local_session, type_schema
from c7n_gcp.resources.resourcemanager import Organization
import jmespath


@Organization.filter_registry.register('essentialcontacts')
class EssentialContactsFilter(ValueFilter):
    """Filter Resources based on essential contacts configuration

    .. code-block:: yaml

      - name: org-essential-contacts
        resource: gcp.organization
        filters:
        - type: essentialcontacts
          org: 99999999
          category: "ALL"
    """
    schema = type_schema('essentialcontacts',
                        org={'type': 'integer'}, category={'type': 'string'}, required=['org'])
    required_keys = {}
    permissions = ("essentialcontacts.contacts.list",)
    annotation_key = 'c7n:matched-findings'

    def process(self, resources, event=None):
        self.findings_list = self.get_findings()
        return [r for r in resources if self.process_resource(r)]

    def get_findings(self):
        self.findings_by_resource = {}
        query_params = {
            'pageSize': 100
        }
        session = local_session(self.manager.session_factory)
        client = session.client("essentialcontacts", "v1", "organizations.contacts")

        findings_paged_list = list(
            client.execute_paged_query(
                'list',
                {'parent': f"organizations/{self.data['org']}", **query_params},
            )
        )
        findings_list = []
        for findings_page in findings_paged_list:
            if findings_page.get('contacts'):
                findings_list.extend(findings_page['contacts'])
        return findings_list

    def process_resource(self, resource):
        filtered_contact = []
        if self.data.get('category'):
            search_path = "[?notificationCategorySubscriptions[?@== '" + \
                self.data.get('category') + "']]"
            filtered_contact = jmespath.search(search_path, self.findings_list)

        return len(filtered_contact) > 0
