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


class SecurityHubTest(BaseTest):
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
