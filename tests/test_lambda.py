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
import json
from mock import patch

from botocore.exceptions import ClientError
from .common import BaseTest, functional
from c7n.executor import MainThreadExecutor
from c7n.resources.awslambda import AWSLambda, ReservedConcurrency
from c7n.mu import PythonPackageArchive


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

    def test_lambda_check_permission(self):
        # lots of pre-conditions, iam role with iam read only policy attached
        # and a permission boundary with deny on iam read access.
        factory = self.replay_flight_data('test_lambda_check_permission')
        p = self.load_policy(
            {
                'name': 'lambda-check',
                'resource': 'lambda',
                'filters': [
                    {'FunctionName': 'custodian-log-age'},
                    {'type': 'check-permissions',
                     'match': 'allowed',
                     'actions': ['iam:ListUsers']}]
            },
            session_factory=factory)
        resources = p.run()
        assert not resources

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
                        "value": '"c7n.metrics"."AWS/Lambda.Invocations.Sum"[0].Sum',
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
            {r["c7n:EventSources"][0] for r in resources}, set(["iot.amazonaws.com"])
        )

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
