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

from .common import BaseTest

import time

LambdaFindingId = "us-east-2/644160558196/81cc9d38b8f8ebfd260ecc81585b4bc9/9f5932aa97900b5164502f41ae393d23" # NOQA


class SecurityHubTest(BaseTest):

    def test_s3_bucket_arn(self):
        policy = self.load_policy({
            'name': 's3',
            'resource': 's3',
            'actions': [
                {'type': 'post-finding',
                 'types': [
                     "Software and Configuration Checks/AWS Security Best Practices/Network Reachability"  # NOQA
                     ]}]})
        post_finding = policy.resource_manager.actions[0]
        resource = post_finding.format_resource(
            {'Name': 'xyz', 'CreationDate': 'xtf'})
        self.assertEqual(resource['Id'], "arn:aws:s3:::xyz")

    def test_bucket(self):
        factory = self.replay_flight_data("test_security_hub_bucket")
        policy = self.load_policy(
            {
                "name": "s3-finding",
                "resource": "s3",
                "filters": [],
                "actions": [
                    {
                        "type": "post-finding",
                        "types": [
                            "Software and Configuration Checks/AWS Security Best Practices/Network Reachability"  # NOQA
                        ],
                    }
                ],
            },
            config={"account_id": "644160558196"},
            session_factory=factory,
        )

        def resources():
            return [
                {
                    "Name": "c7n-test-public-bucket",
                    "CreationDate": "2018-11-26T23:04:52.000Z",
                }
            ]

        self.patch(policy.resource_manager, "resources", resources)
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = factory().client("securityhub")
        findings = client.get_findings(
            Filters={
                "ResourceAwsS3BucketOwnerId": [
                    {"Value": "Unknown", "Comparison": "EQUALS"}
                ],
                "ResourceId": [
                    {
                        "Value": "arn:aws:::c7n-test-public-bucket",
                        "Comparison": "EQUALS",
                    }
                ],
            }
        ).get("Findings")
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["Resources"][0],
            {
                "Details": {"AwsS3Bucket": {"OwnerId": "Unknown"}},
                "Id": "arn:aws:::c7n-test-public-bucket",
                "Region": "us-east-1",
                "Type": "AwsS3Bucket",
            },
        )

    def test_lambda(self):
        # test lambda function via post finding gets tagged with finding id
        factory = self.replay_flight_data('test_security_hub_lambda')
        client = factory().client('lambda')
        func = client.get_function(FunctionName='check')['Configuration']

        def resources():
            return [func]

        policy = self.load_policy({
            'name': 'sec-hub-lambda',
            'resource': 'lambda',
            'actions': [
                {
                    "type": "post-finding",
                    "severity": 10,
                    "severity_normalized": 10,
                    "types": [
                        "Software and Configuration Checks/AWS Security Best Practices"
                    ],
                }]},
            config={"account_id": "644160558196", 'region': 'us-east-2'},
            session_factory=factory)
        self.patch(policy.resource_manager, "resources", resources)
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        func_post_exec = client.get_function(FunctionName='check')
        self.assertEqual(
            func_post_exec['Tags']['c7n:FindingId:sec-hub-lambda'].split(":", 1)[0],
            LambdaFindingId)

    def test_lambda_update(self):
        # test lambda function via post finding, uses tag to update finding.
        factory = self.replay_flight_data('test_security_hub_lambda_update')

        client = factory().client("securityhub", region_name='us-east-2')
        finding_v1 = client.get_findings(
            Filters={
                "Id": [{
                    "Value": LambdaFindingId,
                    "Comparison": "EQUALS",
                }]}).get("Findings")[0]

        lambda_client = factory().client('lambda')
        func = lambda_client.get_function(FunctionName='check')['Configuration']

        def resources():
            return [func]

        policy = self.load_policy({
            'name': 'sec-hub-lambda',
            'resource': 'lambda',
            'actions': [{
                "type": "post-finding",
                "severity": 10,
                "severity_normalized": 10,
                "types": [
                    "Software and Configuration Checks/AWS Security Best Practices"
                ],
            }]},
            config={"account_id": "644160558196", 'region': 'us-east-2'},
            session_factory=factory)
        self.patch(policy.resource_manager, "resources", resources)
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(16)

        finding_v2 = client.get_findings(
            Filters={
                "Id": [{
                    "Value": LambdaFindingId,
                    "Comparison": "EQUALS",
                }]}).get("Findings")[0]

        self.assertNotEqual(finding_v1['UpdatedAt'], finding_v2['UpdatedAt'])

    def test_instance(self):
        factory = self.replay_flight_data("test_security_hub_instance")
        policy = self.load_policy(
            {
                "name": "ec2-finding",
                "resource": "ec2",
                "filters": [],
                "actions": [
                    {
                        "type": "post-finding",
                        "severity": 10,
                        "severity_normalized": 10,
                        "types": [
                            "Software and Configuration Checks/AWS Security Best Practices"
                        ],
                    }
                ],
            },
            config={"account_id": "644160558196"},
            session_factory=factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = factory().client("securityhub")
        findings = client.get_findings(
            Filters={
                "ResourceId": [
                    {
                        "Value": "arn:aws:us-east-1:644160558196:instance/i-0fdc9cff318add68f",
                        "Comparison": "EQUALS",
                    }
                ]
            }
        ).get("Findings")
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["Resources"][0],
            {
                "Details": {
                    "AwsEc2Instance": {
                        "IamInstanceProfileArn": "arn:aws:iam::644160558196:instance-profile/ecsInstanceRole",  # NOQA
                        "ImageId": "ami-0ac019f4fcb7cb7e6",
                        "IpV4Addresses": ["10.205.2.134"],
                        "LaunchedAt": "2018-11-28T22:53:09+00:00",
                        "SubnetId": "subnet-07c118e47bb84cee7",
                        "Type": "t2.micro",
                        "VpcId": "vpc-03005fb9b8740263d",
                    }
                },
                "Id": "arn:aws:us-east-1:644160558196:instance/i-0fdc9cff318add68f",
                "Region": "us-east-1",
                "Tags": {"CreatorName": "kapil", "Name": "bar-run"},
                "Type": "AwsEc2Instance",
            },
        )

    def test_instance_findings_filter(self):
        factory = self.replay_flight_data("test_security_hub_instance_findings_filter")
        policy = self.load_policy(
            {
                "name": "ec2-findings-filter",
                "resource": "ec2",
                "filters": [{
                    "type": "finding",
                    "query": {
                        "Type": [{
                            "Value": "Software and Configuration Checks/AWS Security Best Practices", # NOQA
                            "Comparison": "EQUALS"}]
                    }
                }],
            },
            config={"account_id": "101010101111"},
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_alb_findings_filter(self):
        factory = self.replay_flight_data("test_security_hub_alb_findings_filter")
        policy = self.load_policy(
            {
                "name": "alb-findings-filter",
                "resource": "app-elb",
                "filters": [{
                    "type": "finding",
                    "query": {
                        "Type": [{
                            "Value": "Software and Configuration Checks/AWS Security Best Practices", # NOQA
                            "Comparison": "EQUALS"
                        }]}
                }],
            },
            config={"account_id": "101010101111"},
            session_factory=factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_finding_ec2_arn(self):
        # reuse another tests recorded data to get an ec2 instance
        # not a best practice, avoid if practical.
        factory = self.replay_flight_data("test_security_hub_instance")
        client = factory().client('ec2')
        instances = client.describe_instances().get('Reservations')[0]['Instances']
        policy = self.load_policy({
            'name': 'ec2',
            'resource': 'ec2',
            'actions': [{
                'type': 'post-finding', 'severity': 10,
                'types': ["Software and Configuration Checks/AWS Security Best Practices"]}]},
            config={'region': 'us-east-1', 'account_id': '644160558196'})
        post_finding = policy.resource_manager.actions.pop()
        resource = post_finding.format_resource(instances[0])
        self.assertEqual(
            resource['Id'], 'arn:aws:ec2:us-east-1:644160558196:instance/i-0fdc9cff318add68f')

    def test_iam_user(self):
        factory = self.replay_flight_data("test_security_hub_iam_user")

        policy = self.load_policy(
            {
                "name": "iam-user-finding",
                "resource": "iam-user",
                "filters": [],
                "actions": [
                    {
                        "type": "post-finding",
                        "severity": 10,
                        "severity_normalized": 10,
                        "types": [
                            "Software and Configuration Checks/AWS Security Best Practices"
                        ],
                    }
                ],
            },
            config={"account_id": "101010101111"},
            session_factory=factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = factory().client("securityhub")
        findings = client.get_findings(
            Filters={
                "ResourceId": [
                    {
                        "Value": "arn:aws:iam::101010101111:user/developer",
                        "Comparison": "EQUALS",
                    }
                ]
            }
        ).get("Findings")
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["Resources"][0],
            {
                "Region": "us-east-1",
                "Type": "Other",
                "Id": "arn:aws:iam::101010101111:user/developer",
                "Details": {
                    "Other": {
                        "CreateDate": "2016-09-10T15:45:42+00:00",
                        "UserId": "AIDAJYFPV7WUG3EV7MIIO"
                    }
                }
            }
        )

    def test_iam_role(self):
        factory = self.replay_flight_data("test_security_hub_iam_role")

        policy = self.load_policy(
            {
                "name": "iam-role-finding",
                "resource": "iam-role",
                "filters": [{"type": "value", "key": "RoleName", "value": "app1"}],
                "actions": [
                    {
                        "type": "post-finding",
                        "severity": 10,
                        "severity_normalized": 10,
                        "types": [
                            "Software and Configuration Checks/AWS Security Best Practices"
                        ],
                    }
                ],
            },
            config={"account_id": "101010101111"},
            session_factory=factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = factory().client("securityhub")
        findings = client.get_findings(
            Filters={
                "ResourceId": [
                    {
                        "Value": "arn:aws:iam::1010101011111:role/app1",
                        "Comparison": "EQUALS",
                    }
                ]
            }
        ).get("Findings")
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["Resources"][0],
            {
                "Region": "us-east-1",
                "Type": "Other",
                "Id": "arn:aws:iam::101010101111:role/app1",
                "Details": {
                    "Other": {
                        "RoleName": "app1",
                        "CreateDate": "2017-11-18T22:29:22+00:00",
                        "c7n:MatchedFilters": "[\"tag:CostCenter\", \"tag:Project\"]",
                        "RoleId": "AROAIV5QVPWUHSYPBTURM"
                    }
                }
            }
        )

    def test_iam_profile(self):
        factory = self.replay_flight_data("test_security_hub_iam_profile")

        policy = self.load_policy(
            {
                "name": "iam-profile-finding",
                "resource": "iam-profile",
                "filters": [{
                    "type": "value",
                    "key": "InstanceProfileName",
                    "value": "CloudCustodian"
                }],
                "actions": [
                    {
                        "type": "post-finding",
                        "severity": 10,
                        "severity_normalized": 10,
                        "types": [
                            "Software and Configuration Checks/AWS Security Best Practices"
                        ],
                    }
                ],
            },
            config={"account_id": "101010101111"},
            session_factory=factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = factory().client("securityhub")
        findings = client.get_findings(
            Filters={
                "ResourceId": [
                    {
                        "Value": "arn:aws:iam::101010101111:instance-profile/CloudCustodian",
                        "Comparison": "EQUALS",
                    }
                ]
            }
        ).get("Findings")
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["Resources"][0],
            {
                "Region": "us-east-1",
                "Type": "Other",
                "Id": "arn:aws:iam::101010101111:instance-profile/CloudCustodian",
                "Details": {
                    "Other": {
                        "InstanceProfileId": "AIPAJO63EBUVI2SO6IJFI",
                        "CreateDate": "2018-08-19T22:32:30+00:00",
                        "InstanceProfileName": "CloudCustodian",
                        "c7n:MatchedFilters": "[\"InstanceProfileName\"]"
                    }
                }
            }
        )

    def test_account(self):
        factory = self.replay_flight_data("test_security_hub_account")

        policy = self.load_policy(
            {
                "name": "account-finding",
                "resource": "account",
                "filters": [],
                "actions": [
                    {
                        "type": "post-finding",
                        "severity": 10,
                        "severity_normalized": 10,
                        "types": [
                            "Software and Configuration Checks/AWS Security Best Practices"
                        ],
                    }
                ],
            },
            config={"account_id": "101010101111"},
            session_factory=factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = factory().client("securityhub")
        findings = client.get_findings(
            Filters={
                "ResourceId": [
                    {
                        "Value": "arn:aws:::101010101111:",
                        "Comparison": "EQUALS"
                    }
                ]
            }
        ).get("Findings")
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["Resources"][0],
            {
                "Region": "us-east-1",
                "Type": "Other",
                "Id": "arn:aws:::101010101111:",
                "Details": {
                    "Other": {
                        "account_name": "filiatra-primary"
                    }
                }
            }
        )

    def test_rds(self):
        factory = self.replay_flight_data("test_security_hub_rds")

        policy = self.load_policy(
            {
                "name": "rds-finding",
                "resource": "rds",
                "filters": [
                ],
                "actions": [
                    {
                        "type": "post-finding",
                        "severity": 10,
                        "severity_normalized": 10,
                        "types": [
                            "Software and Configuration Checks/AWS Security Best Practices"
                        ],
                    }
                ],
            },
            config={"account_id": "101010101111"},
            session_factory=factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = factory().client("securityhub")
        findings = client.get_findings(
            Filters={
                "ResourceId": [
                    {
                        "Value": "arn:aws:rds:us-east-1:101010101111:db:testme",
                        "Comparison": "EQUALS",
                    }
                ]
            }
        ).get("Findings")
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["Resources"][0],
            {
                "Details": {
                    "Other": {
                        "Engine": "mariadb",
                        "VpcId": "vpc-d6fe6cb1",
                        "PubliclyAccessible": "False",
                        "DBName": "testme",
                        "AvailabilityZone": "us-east-1a",
                        "InstanceCreateTime": "2018-11-05T03:25:12.384000+00:00",
                        "StorageEncrypted": "False",
                        "AllocatedStorage": "20",
                        "EngineVersion": "10.3.8",
                        "DBInstanceClass": "db.t2.micro",
                        "DBSubnetGroupName": "default"
                    }
                },
                "Region": "us-east-1",
                "Type": "Other",
                "Id": "arn:aws:rds:us-east-1:101010101111:db:testme",
                "Tags": {
                    "workload-type": "other"
                }
            }
        )
