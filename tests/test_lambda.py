# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import time
from unittest.mock import patch

from botocore.exceptions import ClientError
from .common import BaseTest, functional
from c7n.executor import MainThreadExecutor
from c7n.resources.aws import shape_validate
from c7n.resources.awslambda import AWSLambda, ReservedConcurrency
from c7n.mu import PythonPackageArchive
from pytest_terraform import terraform


SAMPLE_FUNC = """\
def handler(event, context):
    print("hello world")
"""


class LambdaPermissionTest(BaseTest):

    def create_function(self, client, name):
        archive = PythonPackageArchive()
        self.addCleanup(archive.remove)
        archive.add_contents("index.py", SAMPLE_FUNC)
        archive.close()

        lfunc = client.create_function(
            FunctionName=name,
            Runtime="python2.7",
            MemorySize=128,
            Handler="index.handler",
            Publish=True,
            Role="arn:aws:iam::644160558196:role/lambda_basic_execution",
            Code={"ZipFile": archive.get_bytes()},
        )
        self.addCleanup(client.delete_function, FunctionName=name)
        return lfunc

    @functional
    def test_lambda_permission_matched(self):
        factory = self.replay_flight_data("test_lambda_permission_matched")
        client = factory().client("lambda")
        name = "func-b"

        self.create_function(client, name)
        client.add_permission(
            FunctionName=name,
            StatementId="PublicInvoke",
            Principal="*",
            Action="lambda:InvokeFunction",
        )
        client.add_permission(
            FunctionName=name,
            StatementId="SharedInvoke",
            Principal="arn:aws:iam::185106417252:root",
            Action="lambda:InvokeFunction",
        )
        p = self.load_policy(
            {
                "name": "lambda-perms",
                "resource": "lambda",
                "filters": [
                    {"FunctionName": name},
                    {"type": "cross-account", "whitelist": ["185106417252"]},
                ],
                "actions": [{"type": "remove-statements", "statement_ids": "matched"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        policy = json.loads(client.get_policy(FunctionName=name).get("Policy"))
        self.assertEqual(
            [s["Sid"] for s in policy.get("Statement", ())], ["SharedInvoke"]
        )

    @functional
    def test_lambda_permission_named(self):
        factory = self.replay_flight_data("test_lambda_permission_named")
        client = factory().client("lambda")
        name = "func-d"

        self.create_function(client, name)
        client.add_permission(
            FunctionName=name,
            StatementId="PublicInvoke",
            Principal="*",
            Action="lambda:InvokeFunction",
        )

        p = self.load_policy(
            {
                "name": "lambda-perms",
                "resource": "lambda",
                "filters": [{"FunctionName": name}],
                "actions": [
                    {"type": "remove-statements", "statement_ids": ["PublicInvoke"]}
                ],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertRaises(ClientError, client.get_policy, FunctionName=name)


def test_function_url_absent(test):
    aws_region = 'us-west-2'
    factory = test.replay_flight_data('test_aws_lambda_function_url', region=aws_region)
    p = test.load_policy({
        'name': 'lambda-function-url',
        'resource': 'aws.lambda',
        'filters': [{'type': 'url-config', 'key': 'FunctionUrl', 'value': 'present'}],
        }, session_factory=factory, config={'region': aws_region})
    resources = p.run()
    assert len(resources) == 1


class LambdaLayerTest(BaseTest):

    def test_lambda_layer_cross_account(self):
        factory = self.replay_flight_data('test_lambda_layer_cross_account')
        p = self.load_policy({
            'name': 'lambda-layer-cross',
            'resource': 'lambda-layer',
            'filters': [{'type': 'cross-account'}],
            'actions': [{'type': 'remove-statements',
                         'statement_ids': 'matched'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('CrossAccountViolations' in resources[0].keys())
        client = factory().client('lambda')
        with self.assertRaises(client.exceptions.ResourceNotFoundException):
            client.get_layer_version_policy(
                LayerName=resources[0]['LayerName'],
                VersionNumber=resources[0]['Version']).get('Policy')

    def test_delete_layer(self):
        factory = self.replay_flight_data('test_lambda_layer_delete')
        p = self.load_policy({
            'name': 'lambda-layer-delete',
            'resource': 'lambda-layer',
            'filters': [{'LayerName': 'test'}],
            'actions': [{'type': 'delete'}]},
            session_factory=factory)
        resources = p.run()
        client = factory().client('lambda')
        with self.assertRaises(client.exceptions.ResourceNotFoundException):
            client.get_layer_version(
                LayerName='test',
                VersionNumber=resources[0]['Version'])


class LambdaTest(BaseTest):

    def test_lambda_update_optimization(self):
        factory = self.replay_flight_data('test_lambda_resize')
        p = self.load_policy(
            {
                'name': 'lambda-update-resize',
                'resource': 'lambda',
                'filters': ['cost-optimization'],
                'actions': ['update']
            },
            session_factory=factory
        )
        resources = p.run()
        assert len(resources) == 1
        client = factory().client('lambda')
        function = client.get_function(FunctionName=resources[0]['FunctionName'])
        assert function['Configuration']['MemorySize'] != resources[0]['MemorySize']

    def test_lambda_trim_versions(self):
        factory = self.replay_flight_data('test_lambda_trim_versions')
        client = factory().client('lambda')
        p = self.load_policy(
            {
                'name': 'lambda-check',
                'resource': 'lambda',
                'actions': [{
                    'type': 'trim-versions',
                    'retain-latest': True
                }]
            },
            session_factory=factory)
        p.resource_manager.actions[0].process(
            [{'FunctionName': 'custodian-ec2-check'}])
        versions = {v['Version']: v for v in
                    client.list_versions_by_function(
                        FunctionName='custodian-ec2-check').get('Versions')}
        aliases = client.list_aliases(
            FunctionName='custodian-ec2-check').get('Aliases')
        assert len(aliases) == 1
        assert aliases[0]['FunctionVersion'] in versions
        assert '$LATEST' in versions
        assert set(versions) == {'$LATEST', '6', '12'}

    def test_lambda_check_permission(self):
        # lots of pre-conditions, iam role with iam read only policy attached
        # and a permission boundary with deny on iam read access.
        factory = self.replay_flight_data('test_lambda_check_permission')
        p = self.load_policy(
            {
                'name': 'lambda-check',
                'resource': 'lambda',
                'filters': [
                    {'FunctionName': 'custodian-ec2-public'},
                    {'type': 'check-permissions',
                     'match': 'allowed',
                     'actions': ['iam:ListUsers']}]
            },
            session_factory=factory)
        resources = p.run()
        assert not resources

        # Re-run, without respecting permission boundaries
        p.data['filters'][1]['boundaries'] = False
        resources = p.run()
        assert len(resources) == 1

    def test_lambda_has_specific_managed_policy(self):
        # lots of pre-conditions, iam role with iam read only policy attached
        # and a permission boundary with deny on iam read access.
        factory = self.replay_flight_data('test_lambda_has_specific_managed_policy')
        p = self.load_policy(
            {
                'name': 'lambda-check',
                'resource': 'lambda',
                'filters': [
                    {'FunctionName': 'cfb-ygaovtob-fail'},
                    {'type': 'has-specific-managed-policy',
                     'value': 'AdministratorAccess'}]
            },
            session_factory=factory)
        resources = p.run()
        assert len(resources) == 1

        # Re-run, without respecting permission boundaries
        p.data['filters'][1]['boundaries'] = False
        resources = p.run()
        assert len(resources) == 1

    def test_lambda_config_source(self):
        factory = self.replay_flight_data("test_aws_lambda_config_source")
        p = self.load_policy(
            {
                "name": "lambda-config",
                "resource": "lambda",
                "source": "config",
                'query': [
                    {'clause': "resourceId = 'omnissm-handle-registrations'"},
                ],
            },
            session_factory=factory, config={'region': 'us-east-2'})

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['FunctionName'], 'omnissm-handle-registrations')
        self.assertEqual(
            resources[0]["Tags"], [{"Key": "lambda:createdBy", "Value": "SAM"}]
        )
        self.assertTrue("c7n:Policy" in resources[0])

    def test_post_finding(self):
        factory = self.replay_flight_data('test_lambda_post_finding')
        p = self.load_policy({
            'name': 'lambda',
            'resource': 'aws.lambda',
            'actions': [
                {'type': 'post-finding',
                 'types': [
                     'Software and Configuration Checks/OrgStandard/abc-123']}]},
            session_factory=factory, config={'region': 'us-west-2'})
        functions = p.resource_manager.get_resources([
            'custodian-ec2-ssm-query'])
        rfinding = p.resource_manager.actions[0].format_resource(functions[0])
        self.maxDiff = None
        self.assertEqual(
            rfinding,
            {'Details': {'AwsLambdaFunction': {
                'CodeSha256': 'Pq32lM46RbVovW/Abh14XfrFHIeUM/cAEC51fwkf+tk=',
                'Code': {
                    'S3Bucket': 'awslambda-us-west-2-tasks',
                    'S3Key': 'snapshots/644160558196/custodian-ec2-ssm-query-c3bed681-aa99-4bb2-a155-2f5897de20d2',  # noqa
                    'S3ObjectVersion': 'Nupr9wOmyG9eZbta8NGFUV9lslQ5NI7m'},
                'Handler': 'custodian_policy.run',
                'LastModified': '2019-07-29T22:37:20.844+0000',
                'MemorySize': 512,
                'RevisionId': '8bbaf510-0ae1-40a5-8980-084bebd3f9c6',
                'Role': 'arn:aws:iam::644160558196:role/CloudCustodianRole',
                'Runtime': 'python3.7',
                'Timeout': 900,
                'TracingConfig': {'Mode': 'PassThrough'},
                'Version': '$LATEST',
                'KmsKeyArn':
                    'arn:aws:kms:us-west-2:644160558196:key/798bc4bb-3079-4a9a-bc27-2c7f2b6c91d0',
                'Environment': {'Variables': {
                    'DISABLE_ACTIONS': 'true',
                    'VERBOSE': 'false',
                    'DISABLE_OUTPUT_PARAMETERS': 'true'}},
                'VpcConfig': {'SecurityGroupIds': [],
                              'SubnetIds': []}}},
             'Id': 'arn:aws:lambda:us-west-2:644160558196:function:custodian-ec2-ssm-query',
             'Partition': 'aws',
             'Region': 'us-west-2',
             'Tags': {'custodian-info': 'mode=config-rule:version=0.8.44.2'},
             'Type': 'AwsLambdaFunction'})
        shape_validate(
            rfinding['Details']['AwsLambdaFunction'],
            'AwsLambdaFunctionDetails', 'securityhub')

    def test_delete(self):
        factory = self.replay_flight_data("test_aws_lambda_delete")
        p = self.load_policy(
            {
                "name": "lambda-events",
                "resource": "lambda",
                "filters": [{"FunctionName": "superduper"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["FunctionName"], "superduper")
        client = factory().client("lambda")
        self.assertEqual(client.list_functions()["Functions"], [])

    def test_delete_reserved_concurrency(self):
        self.patch(ReservedConcurrency, "executor_factory", MainThreadExecutor)
        factory = self.replay_flight_data("test_aws_lambda_delete_concurrency")
        p = self.load_policy(
            {
                "name": "lambda-concurrency",
                "resource": "lambda",
                "filters": [
                    {"FunctionName": "envcheck"},
                    {"type": "reserved-concurrency", "value": "present"},
                ],
                "actions": [{"type": "set-concurrency", "value": None}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["FunctionName"], "envcheck")

        client = factory().client("lambda")
        info = client.get_function(FunctionName=resources[0]["FunctionName"])
        self.assertFalse("Concurrency" in info)

    def test_set_expr_concurrency(self):
        self.patch(ReservedConcurrency, "executor_factory", MainThreadExecutor)
        factory = self.replay_flight_data("test_aws_lambda_set_concurrency_expr")
        p = self.load_policy(
            {
                "name": "lambda-concurrency",
                "resource": "lambda",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "Invocations",
                        "statistics": "Sum",
                        "op": "greater-than",
                        "value": 0,
                    }
                ],
                "actions": [
                    {
                        "type": "set-concurrency",
                        "expr": True,
                        "value": '"c7n.metrics"."AWS/Lambda.Invocations.Sum.14"[0].Sum',
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["FunctionName"], "envcheck")

        client = factory().client("lambda")
        info = client.get_function(FunctionName=resources[0]["FunctionName"])
        self.assertEqual(info["Concurrency"]["ReservedConcurrentExecutions"], 5)

    def test_set_filter_concurrency(self):
        self.patch(ReservedConcurrency, "executor_factory", MainThreadExecutor)
        factory = self.replay_flight_data("test_aws_lambda_set_concurrency")
        p = self.load_policy(
            {
                "name": "lambda-concurrency",
                "resource": "lambda",
                "filters": [{"type": "reserved-concurrency", "value": "absent"}],
                "actions": [{"type": "set-concurrency", "value": 10}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["FunctionName"], "envcheck")

        client = factory().client("lambda")
        info = client.get_function(FunctionName=resources[0]["FunctionName"])
        self.assertEqual(info["Concurrency"]["ReservedConcurrentExecutions"], 10)

    def test_event_source(self):
        factory = self.replay_flight_data("test_aws_lambda_source")
        p = self.load_policy(
            {
                "name": "lambda-events",
                "resource": "lambda",
                "filters": [{"type": "event-source", "key": "", "value": "not-null"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            {r["c7n:EventSources"][0] for r in resources}, {"iot.amazonaws.com"}
        )

    def test_event_source_mapping(self):
        factory = self.record_flight_data("test_aws_lambda_event_source_mapping")
        p = self.load_policy(
            {
                "name": "lambda-event-source",
                "resource": "lambda-event-source-mapping",
                "filters": [
                     {  "tag:team": "policy"
                     }
                 ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn("my-c7n-test", resources[0]["EventSourceArn"])

    def test_sg_filter(self):
        factory = self.replay_flight_data("test_aws_lambda_sg")

        p = self.load_policy(
            {
                "name": "sg-lambda",
                "resource": "lambda",
                "filters": [
                    {"FunctionName": "mys3"},
                    {"type": "security-group", "key": "GroupName", "value": "default"},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(resources[0]["FunctionName"], "mys3")
        self.assertEqual(resources[0]["c7n:matched-security-groups"], ["sg-f9cc4d9f"])

    def test_set_xray_tracing_true(self):
        factory = self.replay_flight_data("test_set_xray_tracing_true")

        p = self.load_policy(
            {
                "name": "xray-lambda",
                "resource": "lambda",
                "filters": [
                    {
                        "type": "value",
                        "key": "TracingConfig.Mode",
                        "value": "PassThrough",
                        "op": "equal"
                    }
                ],
                "actions": [
                    {
                        "type": "set-xray-tracing",
                        "state": True
                    }
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        client = factory().client('lambda')
        response = client.get_function(
            FunctionName=resources[0]['FunctionName'])
        self.assertEqual(response['Configuration']['TracingConfig']['Mode'], 'Active')

    def test_set_xray_tracing_false(self):
        factory = self.replay_flight_data("test_set_xray_tracing_false")

        p = self.load_policy(
            {
                "name": "xray-lambda",
                "resource": "lambda",
                "filters": [
                    {
                        "type": "value",
                        "key": "TracingConfig.Mode",
                        "value": "Active",
                        "op": "equal"
                    }
                ],
                "actions": [
                    {
                        "type": "set-xray-tracing",
                        "state": False
                    }
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        client = factory().client('lambda')
        response = client.get_function(
            FunctionName=resources[0]['FunctionName'])
        self.assertEqual(response['Configuration']['TracingConfig']['Mode'], 'PassThrough')

    def test_lambda_edge(self):
        factory = self.replay_flight_data("test_aws_lambda_edge_filter")
        p = self.load_policy(
            {
                "name": "lambda-edge-filter",
                "resource": "lambda",
                "filters": [{"type": "lambda-edge",
                            "state": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            [r["FunctionName"] for r in resources],
            ["c7n-lambda-edge-new", "test-lambda-edge"])

    def test_lambda_edge_multiple_associations_cache(self):
        factory = self.replay_flight_data("test_lambda_edge_multiple_associations_cache")
        p = self.load_policy(
            {
                "name": "lambda-edge-filter",
                "resource": "lambda",
                "filters": [{"type": "lambda-edge",
                            "state": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            [r["FunctionName"] for r in resources],
            ["c7n-lambda-edge-new", "test-lambda-edge"])


class LambdaTagTest(BaseTest):

    def test_lambda_tag_and_remove(self):
        self.patch(AWSLambda, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_lambda_tag_and_remove")
        client = session_factory().client("lambda")

        policy = self.load_policy(
            {
                "name": "lambda-tag",
                "resource": "lambda",
                "filters": [
                    {"FunctionName": "CloudCustodian"},
                    {"tag:Env": "Dev"},
                ],
                "actions": [
                    {"type": "tag", "key": "xyz", "value": "abcdef"},
                    {"type": "remove-tag", "tags": ["Env"]}
                ]
            },
            session_factory=session_factory, config={
                'account_id': '644160558196',
                'region': 'us-west-2'})

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["FunctionArn"]

        after_tags = client.list_tags(Resource=arn)["Tags"]
        before_tags = {
            t['Key']: t['Value'] for t in resources[0]['Tags']}

        self.assertEqual(before_tags, {'Env': 'Dev'})
        self.assertEqual(after_tags, {'xyz': 'abcdef'})

    def test_mark_and_match(self):
        session_factory = self.replay_flight_data("test_lambda_mark_and_match")
        client = session_factory().client("lambda")
        policy = self.load_policy(
            {
                "name": "lambda-mark",
                "resource": "lambda",
                "filters": [{"FunctionName": "CloudCustodian"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "op": "delete",
                        "tag": "custodian_next",
                        "days": 1,
                    }
                ],
            },
            config={'region': 'us-west-2',
                    'account_id': '644160558196'},
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        arn = resources[0]["FunctionArn"]
        after_tags = client.list_tags(Resource=arn)["Tags"]
        before_tags = {
            t['Key']: t['Value'] for t in resources[0]['Tags']}

        self.assertEqual(before_tags, {'xyz': 'abcdef'})
        self.assertEqual(
            after_tags,
            {'custodian_next': 'Resource does not meet policy: delete@2019/02/09',
             'xyz': 'abcdef'})

    def test_lambda_update_memory_config(self):
        factory = self.replay_flight_data("test_lambda_update_memory_config")
        p = self.load_policy(
            {
                "name": "lambda-update-memory",
                "resource": "lambda",
                "filters": [
                    {"FunctionName": "cloud-custodian-memory-resize-test"}
                ],
                "actions": [
                    {
                        "type": "update",
                        "properties": {"MemorySize": 128}
                    }],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("lambda")
        response = client.get_function(FunctionName=resources[0]['FunctionName'])
        self.assertEqual(response['Configuration']['MemorySize'], 128)
        self.assertEqual(resources[0]['MemorySize'], 256)


class TestModifyVpcSecurityGroupsAction(BaseTest):

    def test_lambda_remove_matched_security_groups(self):

        # Test conditions:
        #   - list with two functions, matching only one "resource-fixer"
        #    - this function is in a VPC and has 3 SGs attached
        #    - removing a third SG, "sg_controllers" (sg-c573e6b3)
        #    - start with 3 SGs, end with 2, match function by regex

        session_factory = self.replay_flight_data(
            "test_lambda_remove_matched_security_groups"
        )

        p = self.load_policy(
            {
                "name": "lambda-remove-matched-security-groups",
                "resource": "lambda",
                "filters": [
                    {
                        "type": "value",
                        "key": "FunctionName",
                        "value": "resource-fixer",
                        "op": "eq",
                    },
                    {
                        "type": "security-group",
                        "key": "GroupName",
                        "value": ".*controllers",
                        "op": "regex",
                    }
                ],
                "actions": [
                    {
                        "type": "modify-security-groups",
                        "remove": "matched",
                        "isolation-group": "sg-01a19f602ecaf25f4",
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        client = session_factory().client('lambda')
        response = client.list_functions()
        clean_resources = response['Functions']

        self.assertEqual(len(resources), 1)
        self.assertIn("fixer", resources[0]["FunctionName"])
        self.assertEqual(len(resources[0]["VpcConfig"]["SecurityGroupIds"]), 3)
        # check result is expected
        self.assertEqual(len(clean_resources[0]["VpcConfig"]["SecurityGroupIds"]), 2)
        self.assertNotIn("sg-c573e6b3", clean_resources[0]["VpcConfig"]["SecurityGroupIds"])
        # verify by name that the removed SG is not there

    def test_lambda_add_security_group(self):

        # Test conditions:
        #   - list with two functions, matching only one "resource-fixer"
        #    - this function is in a VPC and has 2 SGs attached
        #    - adding a third SG, "sg_controllers" (sg-c573e6b3)
        #    - start with 2 SGs, end with 3, match functuin by exact name

        session_factory = self.replay_flight_data("test_lambda_add_security_group")

        p = self.load_policy(
            {
                "name": "add-sg-to-lambda",
                "resource": "lambda",
                "filters": [
                    {
                        "type": "value",
                        "key": "FunctionName",
                        "value": ".*",
                        "op": "regex",
                    },
                ],
                "actions": [{"type": "modify-security-groups", "add": "sg-c573e6b3"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()

        client = session_factory().client('lambda')
        response = client.list_functions()
        clean_resources = response['Functions']

        self.assertEqual(len(resources), 2)
        self.assertEqual("resource-fixer", resources[0]["FunctionName"])
        self.assertEqual(len(resources[0]["VpcConfig"]["SecurityGroupIds"]), 2)
        self.assertNotIn("sg-c573e6b3", resources[0]["VpcConfig"]["SecurityGroupIds"])
        # check SG was added
        self.assertEqual(len(clean_resources[0]["VpcConfig"]["SecurityGroupIds"]), 3)
        self.assertIn("sg-c573e6b3", clean_resources[0]["VpcConfig"]["SecurityGroupIds"])

    def test_nonvpc_function(self):

        session_factory = self.replay_flight_data("test_lambda_add_security_group")

        p = self.load_policy(
            {
                "name": "test-with-nonvpc-lambda",
                "resource": "lambda",
                "filters": [
                    {
                        "type": "value",
                        "key": "FunctionName",
                        "value": "test-func.*",
                        "op": "regex",
                    },
                ],
                "actions": [{"type": "modify-security-groups", "add": "sg-c573e6b3"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual("test-func-2", resources[0]["FunctionName"])

    def test_lambda_notfound_exception(self):
        error_response = {'Error': {'Code': 'ResourceNotFoundException'}}
        operation_name = 'UpdateFunctionConfiguration'
        with patch("c7n.resources.awslambda.local_session") as mock_local_session:
            updatefunc = mock_local_session.client.update_function_configuration
            updatefunc.side_effect = ClientError(error_response, operation_name)
            with self.assertRaises(ClientError):
                groups = ['sg-12121212', 'sg-34343434']
                updatefunc(FunctionName='badname', VpcConfig={'SecurityGroupIds': groups})
                updatefunc.assert_called_once()

    def test_lambda_kms_alias(self):
        session_factory = self.replay_flight_data("test_lambda_kms_key_filter")
        kms = session_factory().client('kms')
        p = self.load_policy(
            {
                "name": "lambda-kms-alias",
                "resource": "lambda",
                "filters": [
                    {
                        'FunctionName': "test"
                    },
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "alias/skunk/trails",
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['KMSKeyArn'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/skunk/trails')


@terraform('aws_lambda_check_permissions', teardown=terraform.TEARDOWN_IGNORE)
def test_lambda_check_permission_deleted_role(test, aws_lambda_check_permissions):
    '''Ensure that the check-permissions filter doesn't raise an exception if
    a Lambda function's role has been deleted.'''

    factory = test.replay_flight_data('test_aws_lambda_check_permission_deleted_role')

    iam_client = factory().client('iam')
    role_name = aws_lambda_check_permissions['aws_iam_role.lambda.name']
    function_name = aws_lambda_check_permissions[
        'aws_lambda_function.test_check_permissions.function_name']

    iam_client.delete_role(RoleName=role_name)
    if test.recording:
        time.sleep(5)

    p = test.load_policy(
        {
            'name': 'lambda-check-deleted-role',
            'resource': 'aws.lambda',
            'filters': [
                {'FunctionName': function_name},
                {'type': 'check-permissions',
                 'match': 'denied',
                 'actions': ['iam:CreateUser']}
            ]
        },
        session_factory=factory)

    resources = p.run()
    test.assertEqual(len(resources), 0)
