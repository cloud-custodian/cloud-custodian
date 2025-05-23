# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
from botocore.exceptions import ClientError
from mock import patch

from .common import BaseTest, event_data
from c7n.exceptions import PolicyValidationError

from pytest_terraform import terraform


@terraform("apigatewayv2_stage")
def test_apigwv2_stage_query(test, apigatewayv2_stage):
    factory = test.replay_flight_data("test_apigwv2_stage_query")

    policy = test.load_policy({
      "name": "test-aws-apigwv2-stage",
      "resource": "aws.apigwv2-stage"
    }, session_factory=factory)

    resources = policy.run()

    assert len(resources) > 0
    assert resources[1]['StageName'] == apigatewayv2_stage[
        'aws_apigatewayv2_stage.example.name']
    assert resources[1]['Tags'] == [{'Key': 'Env', 'Value': 'Dev'}]

    assert policy.resource_manager.get_arns(resources) == [
        'arn:aws:apigateway:us-east-1::/apis/0mt9yx690a/stages/production',
        'arn:aws:apigateway:us-east-1::/apis/zzc87ypck1/stages/example-api-allowed-sheepdog'
    ]


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

    def test_rest_account_exception(self):
        session_factory = self.replay_flight_data('test_rest_account_exception')
        p = self.load_policy(
            {'name': 'rest-account-exception',
             'resource': 'aws.rest-account'},
            session_factory=session_factory
        )
        with self.assertRaises(ClientError) as e:
            p.run()
        self.assertEqual(e.exception.response['Error']['Code'], 'AccessDeniedException')

    def test_rest_account_rate_limit(self):
        session_factory = self.replay_flight_data('test_rest_account_rate_limit')
        p = self.load_policy(
            {'name': 'rest-account-rate-limit',
             'resource': 'aws.rest-account'},
            session_factory=session_factory
        )
        with patch('c7n.utils.time.sleep', new_callable=time.sleep(0)) as func:
            resources = p.run()
        self.assertTrue(func.called)
        self.assertEqual(len(resources), 1)


class TestRestApi(BaseTest):

    def test_rest_api_cross_account(self):
        session_factory = self.replay_flight_data('test_rest_api_cross_account_default')
        p = self.load_policy(
            {'name': 'api-cross-account-default',
             'resource': 'rest-api',
             'filters': [{'type': 'cross-account'}]},
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            resources[0]['CrossAccountViolations'],
            [{'Action': 'execute-api:Invoke',
              'Effect': 'Allow',
              'Principal': '*'}])

    def test_rest_api_update(self):
        session_factory = self.replay_flight_data('test_rest_api_update')
        p = self.load_policy({
            'name': 'update-api',
            'resource': 'rest-api',
            'filters': [
                {'name': 'testapi'},
                {'description': 'for demo only'}
            ],
            'actions': [{
                'type': 'update',
                'patch': [{
                    'op': 'replace',
                    'path': '/description',
                    'value': 'for replacement'}]
            }],
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        updated = session_factory().client('apigateway').get_rest_api(
            restApiId=resources[0]['id'])
        self.assertEqual(updated['description'], 'for replacement')

    def test_rest_api_tag_untag_mark(self):
        session_factory = self.replay_flight_data('test_rest_api_tag_untag_mark')
        client = session_factory().client("apigateway")
        tags = client.get_tags(resourceArn='arn:aws:apigateway:us-east-1::/restapis/dj7uijzv27')
        self.assertEqual(tags.get('tags', {}),
            {'target-tag': 'pratyush'})
        self.maxDiff = None
        p = self.load_policy({
            'name': 'tag-rest-api',
            'resource': 'rest-api',
            'filters': [{'type': 'value', 'key': 'id', 'value': 'dj7uijzv27'}],
            "actions": [
                {'type': 'tag',
                'tags': {'Env': 'Dev'}},
                {'type': 'remove-tag',
                'tags': ['target-tag']},
                {'type': 'mark-for-op', 'tag': 'custodian_cleanup',
                'op': 'update',
                'days': 2}
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.get_tags(resourceArn='arn:aws:apigateway:us-east-1::/restapis/dj7uijzv27')
        self.assertEqual(tags.get('tags', {}),
            {'Env': 'Dev',
            'custodian_cleanup': 'Resource does not meet policy: update@2019/09/11'})

    def test_rest_api_delete(self):
        session_factory = self.replay_flight_data('test_rest_api_delete')
        p = self.load_policy({
            'name': 'tag-rest-api',
            'resource': 'rest-api',
            'filters': [{'tag:target-tag': 'pratyush'}],
            "actions": [{"type": "delete"}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['id'], 'am0c2fyskg')
        client = session_factory().client("apigateway")
        with self.assertRaises(ClientError) as e:
            client.delete_rest_api(restApiId='am0c2fyskg')
        self.assertEqual(e.exception.response['Error']['Code'], 'NotFoundException')

    def test_rest_api_metrics(self):
        factory = self.replay_flight_data("test_rest_api_delete")
        p = self.load_policy(
            {
                "name": "unused-rest-api",
                "resource": "rest-api",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "Count",
                        "days": 4,
                        "period": 86400,
                        "value": 1000,
                        "op": "less-than",
                    }
                ],
            },
            session_factory=factory,
        )
        test_filter = p.resource_manager.filters[0]
        resource_payload = {
            "id": "am0c2fyskg",
            "name": "c7n-test-2"
        }
        test_filter.process(resource_payload)
        self.assertEqual(
            test_filter.get_dimensions(resource_payload),
            [
                {"Name": "ApiName", "Value": "c7n-test-2"}
            ],
        )

    def test_rest_api_has_statement(self):
        session_factory = self.replay_flight_data('test_rest_api_has_statement')
        p = self.load_policy(
            {'name': 'api-has-statement',
             'resource': 'rest-api',
             'filters': [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Allow",
                                "Action": "execute-api:Invoke",
                                "Principal": {
                                    "AWS": "arn:aws:iam::123456789012:root",
                                },
                            },
                            {
                                "Effect": "Allow",
                                "Action": "execute-api:Invoke",
                                "Condition": {
                                    "StringEquals": {
                                        "aws:SourceVpc": ["vpc-1a2b3c4d", "vpc-abc123"]
                                    }
                                }
                            }
                        ]
                    },
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'c7n-test')

        p = self.load_policy(
            {'name': 'api-has-statement',
             'resource': 'rest-api',
             'filters': [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Allow",
                                "Action": "execute-api:Invoke",
                                "Principal": {
                                    "AWS": "arn:aws:iam::123456789012:root",
                                },
                                "PartialMatch": ["Action"],
                            },
                            {
                                "Effect": "Allow",
                                "Action": "execute-api:Invoke",
                                "Condition": {
                                    "StringEquals": {
                                        "aws:SourceVpc": ["vpc-1a2b3c4d", "vpc-abc123"]
                                    }
                                }
                            }
                        ]
                    },
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'c7n-test')


class TestRestResource(BaseTest):

    def test_rest_resource_query(self):
        session_factory = self.replay_flight_data("test_rest_resource_resource")
        p = self.load_policy(
            {"name": "all-rest-resources", "resource": "rest-resource"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(
            sorted([(r["restApiId"], r["path"]) for r in resources]),
            [
                ("5xhc1cnb7h", "/"),
                ("5xhc1cnb7h", "/{proxy+}"),
                ("rtmgxfiay5", "/"),
                ("rtmgxfiay5", "/glenns_test"),
            ],
        )

    def test_rest_integration_filter(self):
        session_factory = self.replay_flight_data("test_rest_integration_filter")
        p = self.load_policy(
            {
                "name": "rest-integration-filter",
                "resource": "aws.rest-resource",
                "filters": [
                    {
                        "type": "rest-integration",
                        "key": "type",
                        "value": "AWS",
                    }
                ],
            }, session_factory=session_factory)

        resources = p.run()

        if len(resources) == 1:
            integrations = resources[0].get('c7n:matched-method-integrations', [])
            if len(integrations) == 1:
                self.assertEqual(integrations[0]['resourceId'], 'ovgcc9m0b7')
            else:
                self.assertFail()
        else:
            self.assertFail()

    def test_rest_integration_delete(self):
        session_factory = self.replay_flight_data("test_rest_integration_delete")
        p = self.load_policy(
            {
                "name": "rest-integration-delete",
                "resource": "rest-resource",
                "filters": [{"type": "rest-integration", "key": "type", "value": "AWS"}],
                "actions": [{"type": "delete-integration"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()

        client = session_factory().client("apigateway")
        integrations = resources[0].get("c7n:matched-method-integrations", [])

        with self.assertRaises(ClientError) as e:
            client.get_integration(
                restApiId=integrations[0]["restApiId"],
                resourceId=integrations[0]['resourceId'],
                httpMethod=integrations[0]["resourceHttpMethod"]
            )
        self.assertEqual(e.exception.response['Error']['Code'], 'NotFoundException')

    def test_rest_integration_update(self):
        session_factory = self.replay_flight_data("test_rest_integration_update")
        p = self.load_policy(
            {
                "name": "rest-integration-update",
                "resource": "rest-resource",
                "filters": [
                    {
                        "type": "rest-integration",
                        "key": "timeoutInMillis",
                        "value": "29000",
                        "op": "not-equal",
                    }
                ],
                "actions": [
                    {
                        "type": "update-integration",
                        "patch": [
                            {
                                "op": "replace",
                                "path": "/timeoutInMillis",
                                "value": "29000",
                            }
                        ],
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        integrations = []
        for r in resources:
            integrations.extend(r["c7n:matched-method-integrations"])

        i = integrations.pop()

        client = session_factory().client("apigateway")

        method = client.get_method(
            restApiId=i["restApiId"],
            resourceId=i["resourceId"],
            httpMethod=i["resourceHttpMethod"],
        )
        self.assertEqual(method['methodIntegration']['timeoutInMillis'], 29000)

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
            methods.extend(r["c7n:matched-resource-methods"])

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

    def test_rest_stage_delete(self):
        session_factory = self.replay_flight_data("test_rest_stage_delete")
        p = self.load_policy(
            {
                "name": "rest-stage-delete",
                "resource": "rest-stage",
                "filters": [{"type": "value", "key": "stageName", "value": "delete-test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        client = session_factory().client("apigateway")
        with self.assertRaises(ClientError) as e:
            client.get_stage(
                restApiId=resources[0]["restApiId"], stageName=resources[0]["stageName"]
            )
        self.assertEqual(e.exception.response['Error']['Code'], 'NotFoundException')

    def test_rest_stage_tag_untag_mark(self):
        session_factory = self.replay_flight_data('test_rest_stage_tag_untag_mark')
        client = session_factory().client("apigateway")
        tags = client.get_tags(
            resourceArn='arn:aws:apigateway:us-east-1::/restapis/l5paassc1h/stages/test')
        self.assertEqual(tags.get('tags', {}),
            {'target-tag': 'pratyush'})
        p = self.load_policy({
            'name': 'tag-rest-stage',
            'resource': 'rest-stage',
            'filters': [{'tag:target-tag': 'pratyush'}],
            "actions": [
                {'type': 'tag',
                'tags': {'Env': 'Dev'}},
                {'type': 'remove-tag',
                'tags': ['target-tag']},
                {'type': 'mark-for-op', 'tag': 'custodian_cleanup',
                'op': 'update',
                'days': 2}
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.get_tags(
            resourceArn='arn:aws:apigateway:us-east-1::/restapis/l5paassc1h/stages/test')
        self.assertEqual(tags.get('tags', {}),
            {'Env': 'Dev',
            'custodian_cleanup': 'Resource does not meet policy: update@2019/11/04'})

    def test_wafv2(self):
        factory = self.replay_flight_data("test_rest_stage_wafv2")
        p = self.load_policy(
            {
                "name": "wafv2-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled", "state": False}],
                "actions": [{"type": "set-wafv2", "web-acl": "testv2", "state": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

        p = self.load_policy(
            {
                "name": "wafv2-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled", "web-acl": "testv2", "state": False}],
                "actions": [{"type": "set-wafv2", "web-acl": "testv2", "state": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

        p = self.load_policy(
            {
                "name": "wafv2-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled", "web-acl": "testv2", "state": True}],
            },
            session_factory=factory,
        )
        self.assertEqual(len(resources), 2)

    def test_reststage_wafv2_filter_regex(self):
        factory = self.replay_flight_data("test_rest_stage_wafv2_regex")

        p = self.load_policy(
            {
                "name": "wafv2-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled", "state": False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

        p = self.load_policy(
            {
                "name": "wafv2-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled",
                             "web-acl": "FMManagedWebACLV2-FMS-T.*",
                             "state": True}],
            },
            session_factory=factory,
            config={'region': 'us-west-2'})
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "wafv2-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled",
                             "web-acl": "testv2",
                             "state": False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_waf(self):
        factory = self.replay_flight_data("test_rest_stage_waf")
        p = self.load_policy(
            {
                "name": "waf-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "waf-enabled", "state": False}],
                "actions": [{"type": "set-waf", "web-acl": "test", "state": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_waf_no_acl(self):
        factory = self.replay_flight_data("test_rest_stage_waf")
        p = self.load_policy(
            {
                "name": "waf-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "waf-enabled", "web-acl": "test", "state": False}],
                "actions": [{"type": "set-waf", "web-acl": "test", "state": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_wafregional_to_wafv2(self):
        factory = self.replay_flight_data("test_rest_stage_waf")
        p = self.load_policy(
            {
                "name": "waf-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "waf-enabled", "state": False}],
                "actions": [{"type": "set-wafv2", "web-acl": "testv2", "state": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_wafregional_to_wafv2_with_acl(self):
        factory = self.replay_flight_data("test_rest_stage_waf")
        p = self.load_policy(
            {
                "name": "waf-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "waf-enabled", "web-acl": "test", "state": False}],
                "actions": [{"type": "set-wafv2", "web-acl": "testv2", "state": True}],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_wafregional_value_no_rules(self):
        factory = self.replay_flight_data("test_rest_stage_waf_value")
        p = self.load_policy(
            {
                "name": "waf-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "waf-enabled", "key": "Rules", "value": "empty"}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_wafregional_value_at_least_1_rule(self):
        factory = self.replay_flight_data("test_rest_stage_waf_value")
        p = self.load_policy(
            {
                "name": "waf-apigw",
                "resource": "rest-stage",
                "filters": [{
                    "type": "waf-enabled",
                    "key": "length(Rules)",
                    "op": "gte",
                    "value": 1
                }]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_wafv2_to_wafregional(self):
        factory = self.replay_flight_data("test_rest_stage_wafv2")
        p = self.load_policy(
            {
                "name": "waf-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled", "state": False}],
                "actions": [{"type": "set-waf", "web-acl": "test", "state": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_wafv2_value_no_rules(self):
        factory = self.replay_flight_data("test_rest_stage_wafv2_value")
        p = self.load_policy(
            {
                "name": "waf-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled", "key": "Rules", "value": "empty"}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_wafv2_value_at_least_1_rule(self):
        factory = self.replay_flight_data("test_rest_stage_wafv2_value")
        p = self.load_policy(
            {
                "name": "waf-apigw",
                "resource": "rest-stage",
                "filters": [{
                    "type": "wafv2-enabled",
                    "key": "length(Rules)",
                    "op": "gte",
                    "value": 1
                }]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_reststage_action_wafv2_not_found(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "wafv2-apigw-set",
                "resource": "rest-stage",
                "filters": [
                    {"state": False}
                ],
                "actions": [
                    {"type": "set-wafv2", "web-acl": "FMManagedWebACLV2-FMS-T.*"}
                ],
            },
        )

    def test_reststage_action_wafv2_state_true(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "wafv2-apigw-set",
                "resource": "rest-stage",
                "filters": [
                    {"type": "wafv2-enabled",
                     "state": True,
                     "web-acl": "FMManagedWebACLV2-FMS.*"}
                ],
                "actions": [
                    {"type": "set-wafv2", "state": True}
                ],
            },
        )

    def test_reststage_action_wafv2_multiple_match(self):
        factory = self.replay_flight_data(
            "test_rest_stage_wafv2_set_action_regex_match")

        p = self.load_policy(
            {
                "name": "wafv2-apigw-set",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled",
                             "state": True}],
                "actions": [{"type": "set-wafv2",
                             "web-acl": "FMManagedWebACLV2-FMS-A.*"}],
            },
            session_factory=factory,
            config={'region': 'us-west-2'})

        with self.assertRaises(ValueError) as ctx:
            p.run()
            self.assertTrue(
                'matching to none or the multiple webacls'
                in str(ctx.exception))

    def test_reststage_action_wafv2_regex_disassociate_webacl(self):
        factory = self.replay_flight_data(
            "test_rest_stage_wafv2_ds_action_regex")

        policy = self.load_policy(
            {
                "name": "wafv2-apigw-set",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled",
                             "web-acl": "FMManagedWebACLV2-FMS-T.*",
                             "state": True}],
                "actions": [
                    {"type": "set-wafv2", "state": False}
                ],
            },
            session_factory=factory,
            config={'region': 'us-west-2'})
        response = policy.run()
        self.assertEqual(response[0]['stageName'], 'test1')

    def test_rest_stage_get_restapi_type(self):
        factory = self.replay_flight_data("test_rest_stage_get_restapi_type")

        policy = self.load_policy(
            {
                "name": "wafv2-apigw-get-restapi",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled",
                             "web-acl": "FMManagedWebACLV2-FMS-T.*",
                             "state": True}],
                "actions": [
                    {"type": "set-wafv2", "state": False}
                ],
            },
            session_factory=factory,
            config={'region': 'us-west-2'})
        response = policy.run()
        self.assertEqual(response[0]['restApiType'], ['REGIONAL'])

    def test_wafv2_to_wafregional_with_acl(self):
        factory = self.replay_flight_data("test_rest_stage_waf")
        p = self.load_policy(
            {
                "name": "waf-apigw",
                "resource": "rest-stage",
                "filters": [{"type": "wafv2-enabled", "web-acl": "testv2", "state": False}],
                "actions": [{"type": "set-waf", "web-acl": "test", "state": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_set_wafv2_active_response(self):
        factory = self.replay_flight_data("test_rest_stage_wafv2")
        policy = self.load_policy(
            {
                "name": "waf-apigw-active-response",
                "resource": "rest-stage",
                "mode": {"type": "cloudtrail", "events": [{
                    "source": "apigateway.amazonaws.com",
                    "ids": "responseElements.deploymentId",
                    "event": "CreateStage"
                }]},
                "filters": [{"type": "wafv2-enabled", "state": False}],
                "actions": [{"type": "set-wafv2", "state": True, "web-acl": "testv2"}],
            },
            session_factory=factory,
        )

        event = {
            "detail": event_data("event-cloud-trail-create-rest-stage.json"),
            "debug": True,
        }
        resources = policy.push(event, None)
        self.assertEqual(len(resources), 1)

    def test_set_wafv2_active_response_tag_resource(self):
        factory = self.replay_flight_data("test_rest_stage_wafv2")
        policy = self.load_policy(
            {
                "name": "waf-apigw-active-response-tag-resource",
                "resource": "rest-stage",
                "mode": {"type": "cloudtrail", "events": [{
                    "source": "apigateway.amazonaws.com",
                    "ids": "requestParameters.resourceArn",
                    "event": "TagResource"
                }]},
                "filters": [{"type": "wafv2-enabled", "state": False}],
                "actions": [{"type": "set-wafv2", "state": True, "web-acl": "testv2"}],
            },
            session_factory=factory,
        )

        resources = policy.push(event_data("event-cloud-trail-tag-rest-stage.json"))
        self.assertEqual(len(resources), 1)

    def test_config_id_stagearn_response(self):
        factory = self.replay_flight_data("test_rest_stage_config_id")
        p = self.load_policy(
            {
                "name": "config_id-apigw-rest-stage-check",
                "resource": "rest-stage",
                "mode": {
                    "type": "config-poll-rule",
                    "role": "arn:aws:iam::{account_id}:role/MyRole",
                    "schedule": "TwentyFour_Hours",
                    "ignore-support-check": True
                }
            },
            session_factory=factory,
            config={'region': 'us-west-2'},
            validate=False
        )
        event = event_data('poll-evaluation.json', 'config')
        results = p.push(event, None)
        self.assertEqual(len(results), 1)

    def test_rest_stage_arn_addition(self):
        factory = self.replay_flight_data("test_rest_stage_arn_addition")
        stagearn = 'arn:aws:apigateway:us-west-2::/restapis/atgw0gohmh/stages/test'
        p = self.load_policy(
            {
                "name": "config_id-apigw-rest-stage-check",
                "resource": "rest-stage",
            },
            session_factory=factory,
            config={'region': 'us-west-2'},
            validate=False
        )
        results = p.run()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['stageArn'], stagearn)


class TestRestClientCertificate(BaseTest):

    def test_rest_client_certificate_resource(self):
        session_factory = self.replay_flight_data('test_rest_client_certificate_resource',
            region='us-east-2')
        p = self.load_policy(
            {
                'name': 'list-rest-client-certificates',
                'resource': 'rest-client-certificate',
            },
            session_factory=session_factory,
            config={'region': 'us-east-2'},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['description'], 'Test certificate')

    def test_rest_stage_client_certificate_filter(self):
        session_factory = self.replay_flight_data(
            'test_rest_stage_client_certificate_filter', region='us-east-2')
        p = self.load_policy(
            {
                'name': 'rest-stages-with-expired-certificate',
                'resource': 'rest-stage',
                'filters': [
                    {
                        'type': 'client-certificate',
                        'key': 'expirationDate',
                        'value_type': 'expiration',
                        'value': 0,
                        'op': 'lte',
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-east-2'},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn('expirationDate', resources[0]['c7n:matched-client-certificate'])

    def test_rest_stage_certificate_filter_config_source(self):
        session_factory = self.replay_flight_data(
            'test_rest_stage_certificate_filter_config_source', region='us-east-2')
        p = self.load_policy(
            {
                'name': 'rest-stages-with-expired-certificate',
                'resource': 'rest-stage',
                'source': 'config',
                'filters': [
                    {
                        'type': 'client-certificate',
                        'key': 'expirationDate',
                        'value_type': 'expiration',
                        'value': 0,
                        'op': 'lte',
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-east-2'},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn('expirationDate', resources[0]['c7n:matched-client-certificate'])


class TestCustomDomainName(BaseTest):
    def test_filter_check_tls(self):
        factory = self.replay_flight_data("test_apigw_domain_name_filter_check_tls")
        p = self.load_policy(
            {
                "name": "apigw-domain-name-check-tls",
                "resource": "apigw-domain-name",
                "filters": [
                    {
                        "not": [
                            {
                                "type": "value",
                                "key": "securityPolicy",
                                "value": "TLS_1_2"
                            }
                        ]
                    }
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["domainName"], "bad.example.com")

    def test_action_remediate_tls(self):
        factory = self.replay_flight_data("test_apigw_domain_name_action_remediate_tls")
        p = self.load_policy(
            {
                "name": "apigw-domain-name-check-tls",
                "resource": "apigw-domain-name",
                "filters": [
                    {
                        "not": [
                            {
                                "type": "value",
                                "key": "securityPolicy",
                                "value": "TLS_1_2"
                            }
                        ]
                    }
                ],
                "actions": [
                    {
                        "type": "update-security",
                        "securityPolicy": "TLS_1_2"
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["domainName"], "bad.example.com")

        # verify resource is remediated
        client = factory().client("apigateway")
        result = client.get_domain_name(domainName="bad.example.com")
        self.assertEqual(result['securityPolicy'], 'TLS_1_2')

    def test_arn_format(self):
        factory = self.replay_flight_data("test_apigw_domain_name_filter_check_tls")
        p = self.load_policy(
            {
                "name": "apigw-domain-name-check-tls",
                "resource": "apigw-domain-name",
                "filters": [
                    {
                        "not": [
                            {
                                "type": "value",
                                "key": "securityPolicy",
                                "value": "TLS_1_2"
                            }
                        ]
                    }
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            p.resource_manager.get_arns(resources)[0],
            "arn:aws:apigateway:us-east-1::/domainnames/bad.example.com"
        )


class TestResourcePolicy(BaseTest):
    def test_rest_api_default_resource_policy(self):
        session_factory = self.replay_flight_data(
            'test_rest_api_default_resource_policy')
        p = self.load_policy({
            'name': 'test-rest-api-default-resource-policy',
            'resource': 'rest-api',
            'filters': [{'type': 'cross-account'}],
            "actions": [{"type": "delete"}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['id'], '6wv8r5sehj')

    def test_rest_api_custom_resource_policy(self):
        session_factory = self.replay_flight_data(
            'test_rest_api_custom_resource_policy')
        p = self.load_policy({
            'name': 'test-rest-api-custom-resource-policy',
            'resource': 'rest-api',
            'filters': [
                {
                    'type': 'cross-account',
                    'whitelist_vpc': ['vpc-011b11111fb2a6b11']
                }
            ],
            "actions": [{"type": "delete"}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['id'], 'kjh6l7usy5')
        self.assertEqual(resources[0]['name'], 'bad-api-gw')


class TestApiGatewayV2Api(BaseTest):

    def test_apigwv2_tag_untag(self):
        session_factory = self.replay_flight_data('test_http_api_tag_untag_mark')
        client = session_factory().client("apigatewayv2")
        p = self.load_policy({
            'name': 'tag-http-api',
            'resource': 'apigwv2',
            'filters': [
                {'tag:name': 'test-http'},
            ],
            "actions": [
                {'type': 'tag',
                'tags': {'Env': 'Dev'}},
                {'type': 'remove-tag',
                'tags': ['name']},
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.get_tags(ResourceArn=p.resource_manager.get_arns(resources)[0])
        self.assertEqual(tags.get('Tags', {}), {'Env': 'Dev'})

    def test_apigwv2_mark(self):
        session_factory = self.replay_flight_data('test_http_api_mark_and_match')
        client = session_factory().client("apigatewayv2")
        p = self.load_policy({
            'name': 'mark-http-api',
            'resource': 'apigwv2',
            'filters': [
                {'ProtocolType': 'WEBSOCKET'},
                {'tag:custodian_cleanup': 'absent'}],
            "actions": [
                {'type': 'mark-for-op', 'tag': 'custodian_cleanup',
                'op': 'notify',
                'days': 2}
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.get_tags(ResourceArn=p.resource_manager.get_arns(resources)[0])
        assert 'custodian_cleanup' in tags['Tags']

    def test_apigwv2_update(self):
        session_factory = self.replay_flight_data('test_apigwv2_api_update')
        client = session_factory().client("apigatewayv2")
        p = self.load_policy(
            {
                'name': 'update-http-api',
                'resource': 'apigwv2',
                'filters': [
                    {'Name': 'c7n-test'}
                ],
                "actions": [
                    {
                        'type': 'update',
                        'CorsConfiguration': {
                            'AllowCredentials': False,
                            'MaxAge': 60,
                        },
                        'Description': 'updated description',
                        "DisableExecuteApiEndpoint": False,
                    }
                ]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n-test')

        api = client.get_api(ApiId=resources[0]['ApiId'])
        self.assertEqual(api['CorsConfiguration'], {
            'AllowCredentials': False,
            'MaxAge': 60,
        })
        self.assertEqual(api['Description'], 'updated description')
        self.assertFalse(api['DisableExecuteApiEndpoint'])

    def test_apigwv2_delete(self):
        session_factory = self.replay_flight_data('test_apigwv2_api_delete')
        client = session_factory().client("apigatewayv2")
        p = self.load_policy(
            {
                'name': 'delete-http-api',
                'resource': 'apigwv2',
                'filters': [
                    {'Name': 'c7n-test'}
                ],
                "actions": [
                    {
                        'type': 'delete',
                    }
                ]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        with self.assertRaises(ClientError) as e:
            client.get_api(ApiId=resources[0]['ApiId'])
        self.assertEqual(e.exception.response['Error']['Code'], 'NotFoundException')


class TestApiGatewayV2Stage(BaseTest):
    def test_apigwv2_stage_update(self):
        session_factory = self.replay_flight_data('test_apigwv2_stage_update')
        client = session_factory().client("apigatewayv2")
        p = self.load_policy(
            {
                'name': 'update-api-stage',
                'resource': 'apigwv2-stage',
                "actions": [
                    {
                        'type': 'update',
                        "AutoDeploy": False,
                        "Description": "new description",
                        'DefaultRouteSettings': {
                            'DetailedMetricsEnabled': False,
                        },
                    }
                ]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        stage = client.get_stage(
            ApiId=resources[0]['c7n:parent-id'],
            StageName=resources[0]['StageName']
        )
        self.assertEqual(stage['DefaultRouteSettings'], {
            'DetailedMetricsEnabled': False,
        })
        self.assertEqual(stage['Description'], 'new description')
        self.assertFalse(stage['AutoDeploy'])

    def test_apigwv2_stage_delete(self):
        session_factory = self.replay_flight_data('test_apigwv2_stage_delete')
        client = session_factory().client("apigatewayv2")
        p = self.load_policy(
            {
                'name': 'delete-api-stage',
                'resource': 'apigwv2-stage',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'StageName',
                        'value': 'c7n-test'
                    }
                ],
                "actions": [
                    {
                        'type': 'delete',
                    }
                ]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        with self.assertRaises(ClientError) as e:
            client.get_stage(
                ApiId=resources[0]['c7n:parent-id'],
                StageName=resources[0]['StageName']
            )
        self.assertEqual(e.exception.response['Error']['Code'], 'NotFoundException')
