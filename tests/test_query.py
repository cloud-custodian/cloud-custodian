# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import logging
import os


from c7n.query import ResourceQuery, RetryPageIterator, TypeInfo
from c7n.resources.vpc import InternetGateway

from botocore.config import Config
from .common import BaseTest, placebo_dir


class ResourceQueryTest(BaseTest):

    def test_pager_with_throttles(self):
        session_factory = self.replay_flight_data('test_query_pagination_retry')
        # at the time of test authoring, there were no retries in the sdk for
        # the describe log groups api, however we also want to override on any
        # sdk config files for unit tests, as well future proof on sdk retry
        # data file updates.
        client = session_factory().client(
            'logs', config=Config(retries={'max_attempts': 0}))

        if self.recording:
            data = json.load(
                open(
                    os.path.join(
                        placebo_dir('test_log_group_last_write'),
                        'logs.DescribeLogGroups_1.json')))
            data['data']['nextToken'] = 'moreplease+kthnxbye'
            self.pill.save_response(
                'logs', 'DescribeLogGroups', data['data'], http_response=200)

            self.pill.save_response(
                'logs', 'DescribeLogGroups',
                {'ResponseMetadata': {
                    "RetryAttempts": 0,
                    "HTTPStatusCode": 200,
                    "RequestId": "dc1f3c1e-a41d-11e6-a2a7-1fd802fe6512",
                    "HTTPHeaders": {
                        "x-amzn-requestid": "dc1f3c1e-a41d-11e6-a2a7-1fd802fe6512",
                        "date": "Sun, 06 Nov 2016 12:38:02 GMT",
                        "content-length": "1621",
                        "content-type": "application/x-amz-json-1.1"
                    }},
                 'Error': {'Code': 'ThrottlingException'}},
                http_response=400)

            self.pill.save_response(
                'logs', 'DescribeLogGroups',
                json.load(
                    open(
                        os.path.join(
                            placebo_dir('test_log_group_retention'),
                            'logs.DescribeLogGroups_1.json')))['data'],
                http_response=200)
            return

        paginator = client.get_paginator('describe_log_groups')
        paginator.PAGE_ITERATOR_CLS = RetryPageIterator
        results = paginator.paginate().build_full_result()
        self.assertEqual(len(results['logGroups']), 11)

    def test_query_filter(self):
        session_factory = self.replay_flight_data("test_query_filter")
        p = self.load_policy(
            {"name": "ec2", "resource": "ec2"}, session_factory=session_factory
        )
        q = ResourceQuery(p.session_factory)
        resources = q.filter(p.resource_manager)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["InstanceId"], "i-9432cb49")

    def test_query_get(self):
        session_factory = self.replay_flight_data("test_query_get")
        p = self.load_policy(
            {"name": "ec2", "resource": "ec2"}, session_factory=session_factory
        )
        q = ResourceQuery(p.session_factory)
        resources = q.get(p.resource_manager, ["i-9432cb49"])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["InstanceId"], "i-9432cb49")

    def test_query_model_get(self):
        session_factory = self.replay_flight_data("test_query_model")
        p = self.load_policy(
            {"name": "igw", "resource": "internet-gateway"},
            session_factory=session_factory,
        )
        q = ResourceQuery(p.session_factory)
        resources = q.filter(p.resource_manager)
        self.assertEqual(len(resources), 3)
        resources = q.get(p.resource_manager, ["igw-3d9e3d56"])
        self.assertEqual(len(resources), 1)

    def test_type_info(self):
        assert repr(TypeInfo) == "<TypeInfo TypeInfo>"


class ConfigSourceTest(BaseTest):

    def test_config_select(self):
        pass

    def test_config_get_query(self):
        p = self.load_policy({'name': 'x', 'resource': 'ec2'})
        source = p.resource_manager.get_source('config')

        # if query passed in reflect it back
        self.assertEqual(
            source.get_query_params({'expr': 'select 1'}),
            {'expr': 'select 1'})

        # if no query passed reflect back policy data
        p.data['query'] = [{'expr': 'select configuration'}]
        self.assertEqual(
            source.get_query_params(None), {'expr': 'select configuration'})

        p.data.pop('query')

        # default query construction
        self.assertTrue(
            source.get_query_params(None)['expr'].startswith(
                'select resourceId, configuration, supplementaryConfiguration where resourceType'))

        p.data['query'] = [{'clause': "configuration.imageId = 'xyz'"}]
        self.assertIn("imageId = 'xyz'", source.get_query_params(None)['expr'])


class QueryResourceManagerTest(BaseTest):

    def test_registries(self):
        self.assertTrue(InternetGateway.filter_registry)
        self.assertTrue(InternetGateway.action_registry)

    def test_resources(self):
        session_factory = self.replay_flight_data("test_query_manager")
        p = self.load_policy(
            {
                "name": "igw-check",
                "resource": "internet-gateway",
                "filters": [{"InternetGatewayId": "igw-2e65104a"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        output = self.capture_logging(
            name=p.resource_manager.log.name, level=logging.DEBUG
        )
        p.run()
        self.assertTrue("Using cached internet-gateway: 3", output.getvalue())

    def test_get_resources(self):
        session_factory = self.replay_flight_data("test_query_manager_get")
        p = self.load_policy(
            {"name": "igw-check", "resource": "internet-gateway"},
            session_factory=session_factory,
        )
        resources = p.resource_manager.get_resources(["igw-2e65104a"])
        self.assertEqual(len(resources), 1)
        resources = p.resource_manager.get_resources(["igw-5bce113f"])
        self.assertEqual(resources, [])

    def test_detail_spec_resource_not_found(self):
        # Test the case where List* API returns a resource that
        # is not found with the Get* API.

        # This test case has two CoreNetworks returned by the ListCoreNetworks API
        # but only one of them is found by the GetCoreNetwork API, since one is a Shared
        # resource from RAM and returns a 404.
        # So the policy should return only 1 CoreNetwork and log a message
        session_factory = self.replay_flight_data("test_networkmanager_core_networks_not_found")
        p = self.load_policy(
            {
                "name": "list-core-networks-not-found",
                "resource": "networkmanager-core",
            },
            session_factory=session_factory,
        )
        # Capture logging to check the output
        output = self.capture_logging(
            name=p.resource_manager.log.name, level=logging.DEBUG
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        for r in resources:
            self.assertTrue(r["CoreNetworkArn"])
            self.assertTrue("Segments" in r)
            self.assertTrue("Edges" in r)

        # Check that the debug message was logged
        self.assertTrue("Resource not found: get_core_network using" in output.getvalue())
        self.assertTrue(resources[0]["CoreNetworkArn"] not in output.getvalue())
