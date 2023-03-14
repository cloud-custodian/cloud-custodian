# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.exceptions import PolicyValidationError
from c7n.resources.aws import shape_validate
from .common import BaseTest, event_data

import logging
import time

LambdaFindingId = "us-east-2/644160558196/81cc9d38b8f8ebfd260ecc81585b4bc9/9f5932aa97900b5164502f41ae393d23" # NOQA


class SecurityHubMode(BaseTest):

    def test_resolve_import_finding(self):
        factory = self.replay_flight_data('test_security_hub_mode_resolve')
        policy = self.load_policy({
            'name': 'trail-fixer',
            'resource': 'aws.iam-user',
            'mode': {
                'type': 'hub-finding',
                'role': 'foo'}},
            session_factory=factory)
        event = event_data("event-securityhub-iamkey-finding-action.json")
        hub = policy.get_execution_mode()
        resources = hub.resolve_import_finding(event)
        self.assertEqual(
            sorted(resources),
            sorted(['arn:aws:iam::644160558196:user/kapil']))
        resources = hub.resolve_resources(event)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['UserName'], 'kapil')

    def test_resolve_action_finding(self):
        policy = self.load_policy({
            'name': 'trail-fixer',
            'resource': 'aws.cloudtrail',
            'mode': {
                'type': 'hub-finding',
                'role': 'foo'}})
        event = event_data("event-securityhub-cloudtrail-finding-action.json")
        hub = policy.get_execution_mode()
        resources = hub.resolve_action_finding(event)
        self.assertEqual(
            sorted(resources),
            sorted([
                'arn:aws:cloudtrail:us-east-1:644160558196:trail/skunk-trails']))

    def test_resolve_action_insight(self):
        factory = self.replay_flight_data(
            "test_security_hub_mode_action_insight")
        policy = self.load_policy({
            'name': 'iam-key',
            'resource': 'aws.iam-user',
            'mode': {
                'type': 'hub-action',
                'role': 'foo'}},
            session_factory=factory)
        hub = policy.get_execution_mode()
        event = event_data("event-securityhub-insight-2.json")
        resources = hub.resolve_action_insight(event)
        self.assertEqual(
            sorted(resources),
            sorted([
                'arn:aws:iam::644160558196:user/brent.clements',
                'arn:aws:iam::644160558196:user/david.shepherd2',
                'arn:aws:iam::644160558196:user/david.yun',
                'arn:aws:iam::644160558196:user/kapil']))

    def test_resolve_multi_account_resource_sets(self):
        factory = self.replay_flight_data(
            'test_security_hub_multi_account_mode')
        policy = self.load_policy({
            'name': 'lambda-remediate',
            'resource': 'aws.lambda',
            'mode': {
                'type': 'hub-action',
                'role': 'CustodianPolicyExecution',
                'member-role': 'arn:aws:iam::{account_id}:role/CustodianGuardDuty'
            }},
            config={'region': 'us-east-2',
                    'account_id': '519413311747'},
            session_factory=factory)
        hub = policy.get_execution_mode()
        event = event_data('event-securityhub-lambda-cross.json')
        partition_resources = hub.get_resource_sets(event)
        self.assertEqual(
            {p: list(map(repr, v)) for p, v in partition_resources.items()},
            {('644160558196', 'us-east-1'): [
                ("<arn:aws:lambda:us-east-1:644160558196:function:"
                 "custodian-enterprise-ec2-instances-no-elastic-ip-isolate>")
            ]})
        output = self.capture_logging(policy.log.name, level=logging.INFO)
        results = hub.run(event, {})
        self.assertIn('Assuming member role:arn:aws:iam::644160558196', output.getvalue())
        self.assertEqual(
            results[('644160558196', 'us-east-1')][0]['FunctionName'],
            'custodian-enterprise-ec2-instances-no-elastic-ip-isolate')


class SecurityHubTest(BaseTest):

    def test_custom_classifier(self):
        templ = {
            'name': 's3',
            'resource': 's3',
            'actions': [{'type': 'post-finding',
                         'types': ['Effects/CustomB/CustomA']}]}
        self.load_policy(templ)
        templ['actions'][0]['types'] = ['CustomA/CustomB/CustomC']
        self.assertRaises(PolicyValidationError, self.load_policy, templ)
        templ['actions'][0]['types'] = ['Effects/CustomB/CustomA/CustomD']
        self.assertRaises(PolicyValidationError, self.load_policy, templ)
        templ['actions'][0]['types'] = []
        self.assertRaises(
            PolicyValidationError, self.load_policy, templ, validate=True)

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
                        'description': 'This one is important',
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
                    "severity_label": "INFORMATIONAL",
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
                    {"DBInstanceArn": "arn:aws:rds:us-west-2:644160558196:db:test-instance-3"}],
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
            config={'region': 'us-west-2', 'account_id': '644160558196'},
            session_factory=factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        rfinding = policy.resource_manager.actions[0].format_resource(resources[0])
        shape_validate(
            rfinding['Details']['AwsRdsDbInstance'],
            'AwsRdsDbInstanceDetails', 'securityhub')

        client = factory().client("securityhub", region_name='us-west-2')
        findings = client.get_findings(
            Filters={
                'Title': [
                    {
                        'Value': 'rds-finding',
                        'Comparison': 'EQUALS'
                    }
                ],
                'ResourceId': [
                    {
                        'Value': 'arn:aws:rds:us-west-2:644160558196:db:test-instance-3',
                        'Comparison': 'EQUALS'
                    }
                ]
            }
        ).get('Findings', [])
        self.assertEqual(len(findings), 1)

        self.assertEqual(
            findings[0]["Resources"][0],
            {
                'Type': 'AwsRdsDbInstance',
                'Id': 'arn:aws:rds:us-west-2:644160558196:db:test-instance-3',
                'Region': 'us-west-2',
                'Details': {
                    'AwsRdsDbInstance': {
                        'CACertificateIdentifier': 'rds-ca-2019',
                        'DBClusterIdentifier': 'test',
                        'DBInstanceIdentifier': 'test-instance-3',
                        'DBInstanceClass': 'db.m5d.xlarge',
                        'DbiResourceId': 'db-EH6SVXMILRMDTBVY4GNOOI3OL4',
                        'Engine': 'postgres',
                        'EngineVersion': '13.7',
                        'KmsKeyId': 'arn:aws:kms:us-west-2:644160558196:key/31e94e00-358a-4f53-8a0c-48ae90c8cc23',  # noqa
                        'StorageEncrypted': True,
                        'VpcSecurityGroups': [
                            {
                                'VpcSecurityGroupId': 'sg-0e255aed9188d1fba',
                                'Status': 'active'
                            }
                        ],
                        'MasterUsername': 'postgres',
                        'AllocatedStorage': 400,
                        'PreferredBackupWindow': '11:55-12:25',
                        'BackupRetentionPeriod': 7,
                        'AvailabilityZone': 'us-west-2b',
                        'PreferredMaintenanceWindow': 'tue:07:49-tue:08:19',
                        'LicenseModel': 'postgresql-license',
                        'Iops': 3000,
                        'OptionGroupMemberships': [
                            {
                                'OptionGroupName': 'default:postgres-13',
                                'Status': 'in-sync'
                            }
                        ],
                        'StorageType': 'io1',
                        'PromotionTier': 1
                    }
                }
            }
        )

    def test_larger_batch_s3(self):
        factory = self.replay_flight_data("test_larger_batch")

        policy = self.load_policy(
            {
                "name": "ebs-finding",
                "resource": "ebs-snapshot",
                "filters": [],
                "actions": [
                    {
                        "type": "post-finding",
                        "severity": 10,
                        "severity_normalized": 10,
                        "batch_size": 2,
                        "title": "EBS Testing",
                        "types": [
                            "Software and Configuration Checks/AWS Security Best Practices"
                        ],
                    }
                ],
            },
            session_factory=factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 2)

        client = factory().client("securityhub")
        findings = client.get_findings(
            Filters={
                "Title": [
                    {
                        "Value": "EBS Testing",
                        "Comparison": "EQUALS",
                    }
                ]
            }
        ).get("Findings")

        self.assertEqual(len(findings), 2)
