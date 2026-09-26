# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import logging
import os
from unittest import mock


from c7n.query import ResourceQuery, RetryPageIterator, TypeInfo, paginate_op
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
        self.assertEqual(
            resources[0]["Instances"][0]["InstanceId"], "i-9432cb49")

    def test_query_get(self):
        session_factory = self.replay_flight_data("test_query_get")
        p = self.load_policy(
            {"name": "ec2", "resource": "ec2"}, session_factory=session_factory
        )
        q = ResourceQuery(p.session_factory)
        resources = q.get(p.resource_manager, ["i-9432cb49"])
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["Instances"][0]["InstanceId"], "i-9432cb49")

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

    def test_config_listed_resources_chunk_failure_raises(self):
        # a failed chunk must not produce a silently partial (and then
        # cached) resource list, every chunk is still attempted and logged.
        p = self.load_policy({'name': 'x', 'resource': 'ec2'})
        source = p.resource_manager.get_source('config')
        ids = ['i-%03d' % i for i in range(120)]
        client = mock.MagicMock()
        client.get_paginator.return_value.paginate.return_value.build_full_result.return_value = {
            'resourceIdentifiers': [{'resourceId': i} for i in ids]}

        attempted = []

        def get_resources(resource_set):
            attempted.append(list(resource_set))
            if 'i-060' in resource_set:
                raise ValueError('config chunk failed')
            return [{'InstanceId': i} for i in resource_set]

        source.get_resources = get_resources
        log = self.capture_logging('custodian.resources', level=logging.ERROR)
        with self.assertRaises(ValueError):
            source.get_listed_resources(client)
        self.assertEqual(len(attempted), 3)
        self.assertIn('config chunk failed', log.getvalue())

        # and without failures every chunk is returned
        source.get_resources = lambda rset: [{'InstanceId': i} for i in rset]
        self.assertEqual(
            sorted(r['InstanceId'] for r in source.get_listed_resources(client)), ids)


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
            name=p.resource_manager.log.name, level=logging.WARNING
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        for r in resources:
            self.assertTrue(r["CoreNetworkArn"])
            self.assertTrue("Segments" in r)
            self.assertTrue("Edges" in r)

        # Check that the warning message was logged
        self.assertTrue("Resource not found: get_core_network using" in output.getvalue())
        self.assertTrue(resources[0]["CoreNetworkArn"] not in output.getvalue())


class GenericPaginationTest(BaseTest):
    """enum ops with a page token but no botocore paginator get paged."""

    def stubbed(self, service, method, pages, **params):
        import boto3
        from botocore.stub import Stubber
        client = boto3.Session(region_name='us-east-1').client(
            service, aws_access_key_id='x', aws_secret_access_key='x')
        self.assertFalse(client.can_paginate(method))
        stubber = Stubber(client)
        for expected, page in pages:
            stubber.add_response(method, page, dict(params, **expected))
        stubber.activate()
        self.addCleanup(stubber.deactivate)
        return client, stubber

    def test_next_token(self):
        client, stubber = self.stubbed('athena', 'list_work_groups', [
            ({}, {'WorkGroups': [{'Name': 'a'}], 'NextToken': 't1'}),
            ({'NextToken': 't1'}, {'WorkGroups': [{'Name': 'b'}]})])
        data = ResourceQuery(None)._invoke_client_enum(
            client, 'list_work_groups', {}, 'WorkGroups')
        self.assertEqual([w['Name'] for w in data], ['a', 'b'])
        stubber.assert_no_pending_responses()

    def test_marker_and_flattened_path(self):
        client, stubber = self.stubbed('rds', 'describe_db_shard_groups', [
            ({}, {'DBShardGroups': [{'DBShardGroupIdentifier': 'a'}], 'Marker': 'm1'}),
            ({'Marker': 'm1'}, {'DBShardGroups': [{'DBShardGroupIdentifier': 'b'}]})])
        data = ResourceQuery(None)._invoke_client_enum(
            client, 'describe_db_shard_groups', {}, 'DBShardGroups[]')
        self.assertEqual([g['DBShardGroupIdentifier'] for g in data], ['a', 'b'])
        stubber.assert_no_pending_responses()

    def test_no_shared_token_single_call(self):
        # wafv2 hands back NextMarker even on single page listings, it is
        # deliberately not paged on
        client, stubber = self.stubbed('wafv2', 'list_web_acls', [
            ({}, {'WebACLs': [{'Name': 'a'}], 'NextMarker': 'a'})], Scope='REGIONAL')
        data = ResourceQuery(None)._invoke_client_enum(
            client, 'list_web_acls', {'Scope': 'REGIONAL'}, 'WebACLs')
        self.assertEqual([w['Name'] for w in data], ['a'])
        stubber.assert_no_pending_responses()

    def test_complex_path_single_call(self):
        client, stubber = self.stubbed('athena', 'list_work_groups', [
            ({}, {'WorkGroups': [{'Name': 'a'}], 'NextToken': 't1'})])
        data = ResourceQuery(None)._invoke_client_enum(
            client, 'list_work_groups', {}, 'WorkGroups[].Name')
        self.assertEqual(data, ['a'])
        stubber.assert_no_pending_responses()

    def test_retry_only_when_asked(self):
        # like the botocore paginator path, the generic one only retries
        # when the manager passes its retry
        def pages():
            # fresh each time, build_full_result extends the first page's list
            return [
                ({}, {'WorkGroups': [{'Name': 'a'}], 'NextToken': 't1'}),
                ({'NextToken': 't1'}, {'WorkGroups': [{'Name': 'b'}]})]
        calls = []

        def retry(func, *args, **kw):
            calls.append(kw)
            return func(*args, **kw)

        with mock.patch.object(RetryPageIterator, 'retry', staticmethod(retry)):
            client, stubber = self.stubbed('athena', 'list_work_groups', pages())
            ResourceQuery(None)._invoke_client_enum(
                client, 'list_work_groups', {}, 'WorkGroups')
            self.assertEqual(calls, [])
            client, stubber = self.stubbed('athena', 'list_work_groups', pages())
            data = ResourceQuery(None)._invoke_client_enum(
                client, 'list_work_groups', {}, 'WorkGroups', retry)
        self.assertEqual([w['Name'] for w in data], ['a', 'b'])
        self.assertEqual(len(calls), 2)
        stubber.assert_no_pending_responses()


class PaginateOpTest(BaseTest):

    def stubbed(self, service, method, pages, **params):
        import boto3
        from botocore.stub import Stubber
        client = boto3.Session(region_name='us-east-1').client(
            service, aws_access_key_id='x', aws_secret_access_key='x')
        stubber = Stubber(client)
        for expected, page in pages:
            stubber.add_response(method, page, dict(params, **expected))
        stubber.activate()
        self.addCleanup(stubber.deactivate)
        return client, stubber

    def test_botocore_paginator(self):
        client, stubber = self.stubbed('logs', 'describe_metric_filters', [
            ({}, {'metricFilters': [{'filterName': 'a'}], 'nextToken': 't1'}),
            ({'nextToken': 't1'}, {'metricFilters': [{'filterName': 'b'}]})],
            logGroupName='trail')
        self.assertTrue(client.can_paginate('describe_metric_filters'))
        self.assertEqual(
            [f['filterName'] for f in paginate_op(
                client, 'describe_metric_filters', 'metricFilters', logGroupName='trail')],
            ['a', 'b'])
        stubber.assert_no_pending_responses()

    def test_generic_paginator(self):
        client, stubber = self.stubbed('lakeformation', 'list_resources', [
            ({}, {'ResourceInfoList': [{'ResourceArn': 'arn:aws:s3:::a'}], 'NextToken': 't1'}),
            ({'NextToken': 't1'}, {'ResourceInfoList': [{'ResourceArn': 'arn:aws:s3:::b'}]})])
        self.assertFalse(client.can_paginate('list_resources'))
        self.assertEqual(
            [r['ResourceArn'] for r in paginate_op(client, 'list_resources', 'ResourceInfoList')],
            ['arn:aws:s3:::a', 'arn:aws:s3:::b'])
        stubber.assert_no_pending_responses()

    def test_no_page_token_single_call(self):
        # NextMarker is not a token the generic paginator pages on
        client, stubber = self.stubbed('wafv2', 'list_logging_configurations', [
            ({}, {'LoggingConfigurations': [], 'NextMarker': 'm1'})], Scope='REGIONAL')
        self.assertEqual(
            paginate_op(
                client, 'list_logging_configurations', 'LoggingConfigurations',
                Scope='REGIONAL'),
            [])
        stubber.assert_no_pending_responses()

    def test_missing_result_key(self):
        client, stubber = self.stubbed('ecs', 'list_clusters', [({}, {})])
        self.assertEqual(paginate_op(client, 'list_clusters', 'clusterArns'), [])
        stubber.assert_no_pending_responses()

    def test_nested_result_key_rejected(self):
        # .get() can't follow a path, it would always come back empty
        client, stubber = self.stubbed('ecs', 'list_clusters', [])
        for key in ('Outer.clusterArns', 'clusterArns[]'):
            with self.assertRaisesRegex(ValueError, 'top level key'):
                paginate_op(client, 'list_clusters', key)
