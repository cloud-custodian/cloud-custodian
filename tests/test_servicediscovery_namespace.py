# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.reports.csvout import Formatter
from .apicallcaptor import ApiCallCaptor
from c7n.resources.servicediscovery import ServiceDiscoveryNamespace
from .common import BaseTest


class TestServiceDiscoveryNamespace(BaseTest):
    def test_servicediscovery_namespace(self):
        # session_factory = self.record_flight_data('test_servicediscovery_namespace')
        session_factory = self.replay_flight_data('test_servicediscovery_namespace')

        # test tags are populated and also the "spec" section
        p = self.load_policy(
            {
                "name": "servicediscovery-namespace-policy",
                "resource": "servicediscovery-namespace",
                "filters": [
                    {
                        "not": [{
                            "type": "value",
                            "key": "Name",
                            "op": "regex",
                            "value": r"^.*\.local$"
                        }]
                    }
                ]

            },
            session_factory=session_factory
        )

        captor = ApiCallCaptor.start_capture()
        # RUN THE SUT
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Id'], 'ns2')
        self.assertEqual(resources[0]['Arn'],
                    'arn:aws:servicediscovery:us-east-1:644160558196:namespace/ns2')
        self.assertEqual(resources[0]['Name'], 'm1')

        arn = p.resource_manager.get_arns(resources)
        self.assertEqual(
            [
                'arn:aws:servicediscovery:us-east-1:644160558196:namespace/ns2'
            ],
            arn,
        )

        # The "placebo" testing library doesn't allow us to make assertions
        # linking specific api's calls to the specific mock response file
        # that will serve that request. So we will compensate here by
        # making an assertion about all the api calls and the order
        # of calls that must be made.
        self.assertEqual(
            [
                {'operation': 'ListNamespaces', 'params': {}, 'service': 'servicediscovery'},
                {'operation': 'GetNamespace',
                 'params': {'Id': 'ns1'},
                 'service': 'servicediscovery'},
                {'operation': 'GetNamespace',
                 'params': {'Id': 'ns2'},
                 'service': 'servicediscovery'},
                {
                    'operation': 'GetResources',
                    'params': {
                        'ResourceARNList': [
                            'arn:aws:servicediscovery:us-east-1:644160558196:namespace/ns1',
                            'arn:aws:servicediscovery:us-east-1:644160558196:namespace/ns2'
                        ]
                    },
                    'service': 'resourcegroupstaggingapi',
                },

            ],
            captor.calls,
        )

    def test_reporting(self):
        f = Formatter(resource_type=ServiceDiscoveryNamespace.resource_type)

        # provide a fake resource
        report = f.to_csv(
            records=[{
                "Id": "ns1",
                "Arn": "arn:aws:servicediscovery:us-east-1:644160558196:namespace/ns1",
                "Name": "testnik.local",
                "Type": "DNS_PRIVATE",
                "Description": "all services will be registered under this common namespace",
                "Properties": {
                    "DnsProperties": {
                        "HostedZoneId": "Z03288441NHEED4TM6QWT",
                        "SOA": {
                            "TTL": 15
                        }
                    },
                    "HttpProperties": {
                        "HttpName": "testnik.local"
                    }
                },
                "CreateDate": "2023-11-03T02:36:27.877000+00:00",
                "CreatorRequestId": "terraform-20240416094214796100000001"
                }
            ]
        )

        headers = list(f.headers())

        # expect Formatter to inspect the definition of certain
        # fields ("id", "name" and "date") from the AppMesh def
        # and to pick out those fields from a fake resource
        self.assertEqual(["Name", "CreateDate"],
                         headers, "header")

        # expect Formatter to inspect the definition of certain
        # fields ("name" and "date") from the AppMesh def
        # and to pick out those fields from a fake resource
        self.assertEqual([["testnik.local", "2023-11-03T02:36:27.877000+00:00"]], report)


class ServiceNamespaceInstance(BaseTest):

    def test_namespace_instance(self):
        # session_factory = self.record_flight_data('test_servicediscovery_instance')
        session_factory = self.replay_flight_data('test_servicediscovery_instance')

        p = self.load_policy(
            {
                "name": "servicediscovery-instance-policy",
                "resource": "servicediscovery-namespace",
                "filters": [
                    {
                        "type": "service-instance",
                        "key": "Services[].Instances[]",
                        "attrs": [
                            {
                                "or": [
                                    {
                                        "Attributes.AWS_EC2_INSTANCE_ID": "present"
                                    },
                                    {
                                        "Attributes.AWS_INIT_HEALTH_STATUS": "present"
                                    },
                                    {
                                        "Attributes.AWS_INSTANCE_IPV6": "present"
                                    },
                                    {
                                        "Attributes.AWS_INSTANCE_PORT": "present"
                                    },
                                    {
                                        "Attributes.AWS_ALIAS_DNS_NAME": "present"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            session_factory=session_factory,
        )

        # RUN THE SUT
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Id'], 'ns-2')
        self.assertEqual(resources[0]['Services'][0]["Id"], 'srv-3')
        self.assertEqual(resources[0]['Services'][0]["Instances"][0]["Id"],
                         'instance-id-1')
