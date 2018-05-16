# Copyright 2018 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from .common import BaseTest


class TestRestAccount(BaseTest):

    def test_missing_rest_account(self):
        session_factory = self.replay_flight_data("test_rest_account_missing")
        p = self.load_policy(
            {"name": "api-account", "resource": "rest-account"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(resources, [])

    def test_rest_api_update(self):
        session_factory = self.replay_flight_data("test_rest_account_update")
        log_role = "arn:aws:iam::644160558196:role/OtherApiGatewayLogger"
        p = self.load_policy(
            {
                "name": "update-account",
                "resource": "rest-account",
                "actions": [
                    {
                        "type": "update",
                        "patch": [
                            {
                                "op": "replace",
                                "path": "/cloudwatchRoleArn",
                                "value": log_role,
                            }
                        ],
                    }
                ],
            },
            session_factory=session_factory,
        )
        before_account, = p.resource_manager._get_account()
        self.assertEqual(
            before_account["cloudwatchRoleArn"],
            "arn:aws:iam::644160558196:role/ApiGwLogger",
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        after_account, = p.resource_manager._get_account()
        self.assertEqual(after_account["cloudwatchRoleArn"], log_role)


class TestRestResource(BaseTest):

    def test_rest_resource_query(self):
        session_factory = self.replay_flight_data("test_rest_resource_resource")
        p = self.load_policy(
            {"name": "all-rest-resources", "resource": "rest-resource"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 4)
        self.assertEqual(
            sorted([(r["restApiId"], r["path"]) for r in resources]),
            [
                ("5xhc1cnb7h", "/"),
                ("5xhc1cnb7h", "/{proxy+}"),
                ("rtmgxfiay5", "/"),
                ("rtmgxfiay5", "/glenns_test"),
            ],
        )

    def test_rest_resource_method_update(self):
        session_factory = self.replay_flight_data("test_rest_resource_method_update")
        p = self.load_policy(
            {
                "name": "rest-method-iam",
                "resource": "rest-resource",
                "filters": [
                    {
                        "type": "rest-method",
                        "key": "authorizationType",
                        "value": "AWS_IAM",
                        "op": "not-equal",
                    }
                ],
                "actions": [
                    {
                        "type": "update-method",
                        "patch": [
                            {
                                "op": "replace",
                                "path": "/authorizationType",
                                "value": "AWS_IAM",
                            }
                        ],
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        methods = []
        for r in resources:
            methods.extend(r["c7n-matched-resource-methods"])
        # resource = resources.pop()

        m = methods.pop()
        client = session_factory().client("apigateway")

        method = client.get_method(
            restApiId=m["restApiId"],
            resourceId=m["resourceId"],
            httpMethod=m["httpMethod"],
        )
        self.assertEqual(method["authorizationType"], "AWS_IAM")


class TestRestStage(BaseTest):

    def test_rest_stage_resource(self):
        session_factory = self.replay_flight_data("test_rest_stage")
        p = self.load_policy(
            {
                "name": "all-rest-stages",
                "resource": "rest-stage",
                "filters": [{"tag:ENV": "DEV"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["stageName"], "latest")

    def test_rest_stage_update(self):
        session_factory = self.replay_flight_data("test_rest_stage_update")
        p = self.load_policy(
            {
                "name": "rest-stage-update",
                "resource": "rest-stage",
                "filters": [{'methodSettings."*/*".loggingLevel': "absent"}],
                "actions": [
                    {
                        "type": "update",
                        "patch": [
                            {
                                "op": "replace",
                                "path": "/*/*/logging/dataTrace",
                                "value": "true",
                            },
                            {
                                "op": "replace",
                                "path": "/*/*/logging/loglevel",
                                "value": "info",
                            },
                        ],
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 2)
        client = session_factory().client("apigateway")

        stage = client.get_stage(
            restApiId=resources[0]["restApiId"], stageName=resources[0]["stageName"]
        )

        found = False
        for k, m in stage.get("methodSettings", {}).items():
            found = True
            self.assertEqual(m["loggingLevel"], "INFO")
            self.assertEqual(m["dataTraceEnabled"], True)
        self.assertTrue(found)
