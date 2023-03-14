# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest, event_data


class CloudSearch(BaseTest):

    def test_resource_manager(self):
        factory = self.replay_flight_data("test_cloudsearch_query")
        p = self.load_policy(
            {
                "name": "cs-query",
                "resource": "cloudsearch",
                "filters": [{"DomainName": "sock-index"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DomainName"], "sock-index")

    def test_delete_search(self):
        factory = self.replay_flight_data("test_cloudsearch_delete")
        p = self.load_policy(
            {
                "name": "csdel",
                "resource": "cloudsearch",
                "filters": [{"DomainName": "sock-index"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("cloudsearch")
        state = client.describe_domains(DomainNames=["sock-index"])["DomainStatusList"][
            0
        ]
        self.assertEqual(state["Deleted"], True)

    def test_enable_https_cloud_search(self):
        """ CloudSearchEnableHttpsTest: tes_enable_https_cloud_search: enable https """
        session_factory = self.replay_flight_data("test_enable_https_cloud_search")
        p = self.load_policy(
            {
                "name": "cloudsearch-enable-https",
                "resource": "cloudsearch",
                "mode": {
                    "type": "cloudtrail",
                    "events": [
                        {
                            "event": "CreateDomain",
                            "source": "cloudsearch.amazonaws.com",
                            "ids": "requestParameters.domainName"
                        }
                    ]
                },
                "actions": [
                    {
                        "type": "enable-https",
                        "tls-policy": "Policy-Min-TLS-1-2-2019-07"
                    }
                ],
                "filters": [{
                    "type": "domain-options",
                    "key": "Options.EnforceHTTPS",
                    "value": False,
                }]
            },
            session_factory=session_factory
        )
        event = event_data("event-cloudsearch.json", "config")
        resources = p.push(event, {})
        client = session_factory().client('cloudsearch')
        for resource in resources:
            self.assert_cloudsearch_https(client, resource)

    def assert_cloudsearch_https(self, client, resource):
        """
        Tests that https flag set to true
        Args:
            resource: cloudsearch resource
            client (obj): aws cloudsearch client
        """
        domain_name = resource['DomainName']
        response = client.describe_domain_endpoint_options(
            DomainName=domain_name)
        https_status = response['DomainEndpointOptions']['Options']['EnforceHTTPS']
        self.assertEqual(https_status, True, 'cloud search https is enabled')
