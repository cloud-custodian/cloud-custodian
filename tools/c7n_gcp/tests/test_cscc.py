# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_gcp.actions.cscc import ResourceNameAdapters

from gcp_common import BaseTest


class PostFinding(BaseTest):

    def test_cscc_post(self):
        factory = self.replay_flight_data('cscc-post-finding')
        session = factory()
        findings = session.client(
            'securitycenter', 'v1', 'organizations.sources.findings')

        p = self.load_policy({
            'name': 'sketchy-drive',
            'resource': 'gcp.disk',
            'filters': [{'name': 'instance-1'}],
            'actions': [
                {'type': 'post-finding',
                 'org-domain': 'example.io'}
            ]},
            session_factory=factory)

        post_finding = p.resource_manager.actions[0]
        resources = p.run()
        self.assertEqual(len(resources), 1)
        resource = resources.pop()
        self.assertEqual(resource['name'], 'instance-1')

        source = post_finding.initialize_source()

        results = findings.execute_query(
            'list', {'parent': source}).get('findings', [])
        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]['sourceProperties']['resource-type'], 'disk')


class NameResolver(BaseTest):

    def assertName(self, service, src, expected):
        self.assertEqual(
            ResourceNameAdapters[service](src), expected)

    def test_resource_project_name(self):
        self.assertName(
            "cloudresourcemanager",
            {'projectId': 'test-226520', 'projectNumber': '435820424010'},
            "//cloudresourcemanager.googleapis.com/projects/435820424010")

    def test_resource_org_name(self):
        self.assertName(
            "cloudresourcemanager",
            {"organizationId": "851339424791"},
            "//cloudresourcemanager.googleapis.com/organizations/851339424791")

    def test_gke_cluster_naem(self):
        self.assertName(
            "container",
            {'selfLink': 'https://container.googleapis.com/v1/projects/test-226520/zones/us-central1-a/clusters/dev-cluster'}, # noqa
            "//container.googleapis.com/projects/test-226520/zones/us-central1-a/clusters/dev-cluster") # noqa

    def test_service_account_name(self):
        self.assertName(
            "iam",
            {'projectId': 'test-226520', 'uniqueId': 108649139393552775748},
            "//iam.googleapis.com/projects/test-226520/serviceAccounts/108649139393552775748")

    def test_appengine_name(self):
        self.assertName(
            "appengine",
            {'name': 'apps/test-226520'},
            "//appengine.googleapis.com/apps/test-226520")

    def test_compute_name(self):
        self.assertName(
            "compute",
            {'id': 3933994916372270321,
             'selfLink': 'https://www.googleapis.com/compute/v1/projects/test-226520/zones/us-east1-b/instances/instance-1'}, # noqa
            "//compute.googleapis.com/projects/test-226520/zones/us-east1-b/instances/3933994916372270321") # noqa

    def test_bucket_name(self):
        self.assertName(
            "storage",
            {'name': 'c7n-org-devtest'},
            "//storage.googleapis.com/c7n-org-devtest")
