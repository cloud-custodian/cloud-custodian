# Copyright 2016-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from .common import BaseTest

from c7n.resources.aws import shape_validate


class ElasticSearch(BaseTest):

    def test_get_resources(self):
        factory = self.replay_flight_data('test_elasticsearch_get')
        p = self.load_policy({
            'name': 'es-get',
            'resource': 'aws.elasticsearch'},
            session_factory=factory)
        resources = p.resource_manager.get_resources(['devx'])
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['DomainName'], 'devx')

    def test_resource_manager(self):
        factory = self.replay_flight_data("test_elasticsearch_query")
        p = self.load_policy(
            {
                "name": "es-query",
                "resource": "elasticsearch",
                "filters": [{"DomainName": "c7n-test"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DomainName"], "c7n-test")
        self.assertEqual(resources[0]["Tags"], [{u"Key": u"Env", u"Value": u"Dev"}])
        self.assertTrue(
            resources[0]["Endpoint"].startswith(
                "search-c7n-test-ug4l2nqtnwwrktaeagxsqso"
            )
        )

    def test_metrics_domain(self):
        factory = self.replay_flight_data("test_elasticsearch_delete")
        p = self.load_policy(
            {
                "name": "es-query",
                "resource": "elasticsearch",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "SearchableDocuments",
                        "days": 4,
                        "period": 86400,
                        "value": 1000,
                        "op": "less-than",
                    }
                ],
            },
            session_factory=factory,
        )
        self.assertEqual(
            p.resource_manager.filters[0].get_dimensions({"DomainName": "foo"}),
            [
                {"Name": "ClientId", "Value": "644160558196"},
                {"Name": "DomainName", "Value": "foo"},
            ],
        )

    def test_delete_search(self):
        factory = self.replay_flight_data("test_elasticsearch_delete")
        p = self.load_policy(
            {
                "name": "es-query",
                "resource": "elasticsearch",
                "filters": [{"DomainName": "c7n-test"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DomainName"], "c7n-test")

        client = factory().client("es")

        state = client.describe_elasticsearch_domain(DomainName="c7n-test")[
            "DomainStatus"
        ]
        self.assertEqual(state["Deleted"], True)

    def test_post_finding_es(self):
        factory = self.replay_flight_data('test_elasticsearch_post_finding')
        p = self.load_policy({
            'name': 'es-post',
            'resource': 'aws.elasticsearch',
            'actions': [
                {'type': 'post-finding',
                 'types': [
                     'Software and Configuration Checks/OrgStandard/abc-123']}]},
            session_factory=factory, config={'region': 'us-west-2'})
        resources = p.resource_manager.resources()
        self.maxDiff = None
        self.assertEqual(len(resources), 1)
        fresource = p.resource_manager.actions[0].format_resource(resources[0])
        self.assertEqual(
            fresource['Details']['AwsElasticsearchDomain'],
            {'AccessPolicies': '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":"*"},"Action":"es:*","Resource":"arn:aws:es:us-west-2:644160558196:domain/devx/*"}]}',  # noqa
             'DomainEndpointOptions': {
                 'EnforceHTTPS': True,
                 'TLSSecurityPolicy': 'Policy-Min-TLS-1-0-2019-07'},
             'DomainId': '644160558196/devx',
             'DomainName': 'devx',
             'Endpoints': {
                 'vpc': 'vpc-devx-4j4l2ateukiwrnnxgbowppjt64.us-west-2.es.amazonaws.com'},
             'ElasticsearchVersion': '7.4',
             'EncryptionAtRestOptions': {
                 'Enabled': True,
                 'KmsKeyId': 'arn:aws:kms:us-west-2:644160558196:key/9b776c6e-0a40-45d0-996b-707018677fe9'  # noqa
             },
             'NodeToNodeEncryptionOptions': {'Enabled': True},
             'VPCOptions': {'AvailabilityZones': ['us-west-2b'],
                            'SecurityGroupIds': ['sg-0eecc076'],
                            'SubnetIds': ['subnet-63c97615'],
                            'VPCId': 'vpc-4a9ff72e'}})
        shape_validate(
            fresource['Details']['AwsElasticsearchDomain'],
            'AwsElasticsearchDomainDetails',
            'securityhub')

    def test_domain_add_tag(self):
        session_factory = self.replay_flight_data("test_elasticsearch_add_tag")
        client = session_factory(region="us-east-1").client("es")
        p = self.load_policy(
            {
                "name": "tag-elasticsearch-domain",
                "resource": "elasticsearch",
                "filters": [{"tag:MyTag": "absent"}],
                "actions": [{"type": "tag", "key": "MyTag", "value": "MyValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DomainName"], "c7n-test")
        tags = client.list_tags(ARN=resources[0]["ARN"])["TagList"][0]
        self.assertEqual(tags, {"Key": "MyTag", "Value": "MyValue"})

    def test_domain_remove_tag(self):
        session_factory = self.replay_flight_data("test_elasticsearch_remove_tag")
        client = session_factory(region="us-east-1").client("es")
        p = self.load_policy(
            {
                "name": "remove-tag-elasticsearch-domain",
                "resource": "elasticsearch",
                "filters": [{"tag:MyTag": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["MyTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DomainName"], "c7n-test")
        tags = client.list_tags(ARN=resources[0]["ARN"])["TagList"]
        self.assertEqual(len(tags), 0)

    def test_domain_mark_for_op(self):
        session_factory = self.replay_flight_data("test_elasticsearch_markforop")
        client = session_factory(region="us-east-1").client("es")
        p = self.load_policy(
            {
                "name": "markforop-elasticsearch-domain",
                "resource": "elasticsearch",
                "filters": [{"tag:MyTag": "absent"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "days": 1,
                        "tag": "es_custodian_cleanup",
                        "op": "delete",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DomainName"], "c7n-test")
        tags = client.list_tags(ARN=resources[0]["ARN"])["TagList"][0]
        self.assertEqual(
            tags,
            {
                "Key": "es_custodian_cleanup",
                "Value": "Resource does not meet policy: delete@2017/11/30",
            },
        )

    def test_domain_marked_for_op(self):
        session_factory = self.replay_flight_data("test_elasticsearch_markedforop")
        p = self.load_policy(
            {
                "name": "markedforop-elasticsearch-domain",
                "resource": "elasticsearch",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "es_custodian_cleanup",
                        "skew": 1,
                        "op": "delete",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DomainName"], "c7n-test")

    def test_modify_security_groups(self):
        session_factory = self.replay_flight_data(
            "test_elasticsearch_modify_security_groups"
        )
        p = self.load_policy(
            {
                "name": "modify-es-sg",
                "resource": "elasticsearch",
                "filters": [
                    {
                        "type": "security-group",
                        "key": "GroupId",
                        "value": ["sg-6c7fa917", "sg-3839ec4b"],
                        "op": "in",
                    }
                ],
                "actions": [
                    {
                        "type": "modify-security-groups",
                        "add": ["sg-9a5386e9"],
                        "remove": ["sg-3839ec4b"],
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(
            sorted(resources[0]["VPCOptions"]["SecurityGroupIds"]),
            sorted(["sg-6c7fa917", "sg-3839ec4b"]),
        )

        client = session_factory(region="us-east-1").client("es")
        result = client.describe_elasticsearch_domains(
            DomainNames=[resources[0]["DomainName"]]
        )[
            "DomainStatusList"
        ]
        self.assertEqual(
            sorted(result[0]["VPCOptions"]["SecurityGroupIds"]),
            sorted(["sg-6c7fa917", "sg-9a5386e9"]),
        )


class TestReservedInstances(BaseTest):

    def test_elasticsearch_reserved_node_query(self):
        session_factory = self.replay_flight_data("test_elasticsearch_reserved_instances_query")
        p = self.load_policy(
            {
                "name": "elasticsearch-reserved",
                "resource": "aws.elasticsearch-reserved"
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["ReservedElasticsearchInstanceId"],
            "036381d0-4fa5-4484-bd1a-efc1b43af0bf"
        )
