# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import unittest
from mock import Mock, patch

from c7n_mailer import utils


class FormatStruct(unittest.TestCase):

    def test_formats_struct(self):
        expected = '{\n  "foo": "bar"\n}'
        actual = utils.format_struct({'foo': 'bar'})
        self.assertEqual(expected, actual)


class StripPrefix(unittest.TestCase):

    def test_strip_prefix(self):
        self.assertEqual(utils.strip_prefix('aws.internet-gateway', 'aws.'), 'internet-gateway')
        self.assertEqual(utils.strip_prefix('aws.s3', 'aws.'), 's3')
        self.assertEqual(utils.strip_prefix('aws.webserver', 'aws.'), 'webserver')
        self.assertEqual(utils.strip_prefix('nothing', 'aws.'), 'nothing')
        self.assertEqual(utils.strip_prefix('azure.azserver', 'azure.'), 'azserver')
        self.assertEqual(utils.strip_prefix('', 'aws.'), '')


class ResourceFormat(unittest.TestCase):

    def test_efs(self):
        self.assertEqual(
            utils.resource_format(
                {'Name': 'abc', 'FileSystemId': 'fsid', 'LifeCycleState': 'available'},
                'efs'),
            'name: abc  id: fsid  state: available')

    def test_eip(self):
        self.assertEqual(
            utils.resource_format(
                {'PublicIp': '8.8.8.8', 'Domain': 'vpc', 'AllocationId': 'eipxyz'},
                'network-addr'),
            'ip: 8.8.8.8  id: eipxyz  scope: vpc')

    def test_nat(self):
        self.assertEqual(
            utils.resource_format(
                {'NatGatewayId': 'nat-xyz', 'State': 'available', 'VpcId': 'vpc-123'},
                'nat-gateway'),
            'id: nat-xyz  state: available  vpc: vpc-123')

    def test_igw(self):
        self.assertEqual(
            utils.resource_format(
                {'InternetGatewayId': 'igw-x', 'Attachments': []},
                'aws.internet-gateway'),
            'id: igw-x  attachments: 0')

    def test_s3(self):
        self.assertEqual(
            utils.resource_format(
                {'Name': 'bucket-x'}, 'aws.s3'),
            'bucket-x')

    def test_alb(self):
        self.assertEqual(
            utils.resource_format(
                {'LoadBalancerArn':
                    'arn:aws:elasticloadbalancing:us-east-1:367930536793:'
                    'loadbalancer/app/dev/1234567890',
                 'AvailabilityZones': [], 'Scheme': 'internal'},
                'app-elb'),
            'arn: arn:aws:elasticloadbalancing:us-east-1:367930536793:'
            'loadbalancer/app/dev/1234567890'
            '  zones: 0  scheme: internal')

    def test_acm_certificate(self):
        self.assertEqual(
            utils.resource_format(
                {'DomainName': 'domain-x', 'Subject': 'CN=domain-x', 'Status': 'ISSUED'},
                'acm-certificate'),
            'domain-x CN=domain-x status: ISSUED')

    def test_app_elb_target_group(self):
        self.assertEqual(
            utils.resource_format(
                {'TargetGroupName': 'tg-x', 'VpcId': 'vpcid349a'}, 'app-elb-target-group'),
            'tg-x vpcid349a')

    def test_eks(self):
        self.assertEqual(
            utils.resource_format(
                {'name': 'eks-x', 'status': 'ACTIVE'}, 'eks'),
            'eks-x status: ACTIVE')

    def test_elasticsearch(self):
        self.assertEqual(
            utils.resource_format(
                {'DomainName': 'es-x'}, 'elasticsearch'),
            'es-x')

    def test_firehose(self):
        self.assertEqual(
            utils.resource_format(
                {'DeliveryStreamName': 'fh-x', 'DeliveryStreamStatus': 'ACTIVE'}, 'firehose'),
            'fh-x status: ACTIVE')

    def test_kms(self):
        self.assertEqual(
            utils.resource_format(
                {'AliasName': 'alias-x', 'TargetKeyId': 'tki-1234'}, 'kms'),
            'alias-x tki-1234')

    def test_kms_key(self):
        self.assertEqual(
            utils.resource_format(
                {'KeyId': 'keyid-x', 'Description': 'desc', 'KeyState': 'Enabled',
                 'Tags': [{'Key': 'Name', 'Value': 'kms-key-name'}]}, 'kms-key'),
            'keyid-x kms-key-name desc keystate: Enabled')

    def test_rds_cluster(self):
        self.assertEqual(
            utils.resource_format(
                {'DBClusterIdentifier': 'dbclusterid-x', 'Engine': 'dbengine',
                'EngineVersion': '1.0', 'AllocatedStorage': '1', 'Status': 'available'},
                'rds-cluster'),
            'dbclusterid-x dbengine-1.0 1 available')

    def test_secrets_manager(self):
        self.assertEqual(
            utils.resource_format(
                {'Name': 'sm-x'}, 'secrets-manager'),
            'sm-x')

    def test_sns(self):
        self.assertEqual(
            utils.resource_format(
                {'TopicArn': 'arn-x', 'DisplayName': 'name-1234'}, 'sns'),
            'arn-x name-1234')

    def test_ssm_parameter(self):
        self.assertEqual(
            utils.resource_format(
                {'Name': 'ssm-parameter-x'}, 'ssm-parameter'),
            'ssm-parameter-x')

    def test_user_pool(self):
        self.assertEqual(
            utils.resource_format(
                {'Name': 'user-pool-x'}, 'user-pool'),
            'user-pool-x')


class GetAwsUsernameFromEvent(unittest.TestCase):

    # note principalId is very org/domain specific for federated?, it would be
    # good to get confirmation from capone on this event / test.
    CLOUDTRAIL_EVENT = {
        'detail': {
            'userIdentity': {
                "type": "IAMUser",
                "principalId": "AIDAJ45Q7YFFAREXAMPLE",
                "arn": "arn:aws:iam::123456789012:user/michael_bolton",
                "accountId": "123456789012",
                "accessKeyId": "AKIAIOSFODNN7EXAMPLE",
                "userName": "michael_bolton"
            }
        }
    }

    def test_get(self):
        username = utils.get_aws_username_from_event(
            Mock(), self.CLOUDTRAIL_EVENT
        )
        self.assertEqual(username, 'michael_bolton')

    def test_get_username_none(self):
        self.assertEqual(
            utils.get_aws_username_from_event(Mock(), None),
            None
        )

    def test_get_username_identity_none(self):
        evt = {'detail': {}}
        self.assertEqual(
            utils.get_aws_username_from_event(Mock(), evt),
            None
        )

    def test_get_username_assumed_role(self):
        evt = {
            'detail': {
                'userIdentity': {
                    'type': 'AssumedRole',
                    'arn': 'foo'
                }
            }
        }
        self.assertEqual(
            utils.get_aws_username_from_event(Mock(), evt),
            'foo'
        )

    def test_get_username_assumed_role_instance(self):
        evt = {
            'detail': {
                'userIdentity': {
                    'type': 'AssumedRole',
                    'arn': 'foo/i-12345678'
                }
            }
        }
        self.assertEqual(
            utils.get_aws_username_from_event(Mock(), evt),
            None
        )

    def test_get_username_assumed_role_lambda(self):
        evt = {
            'detail': {
                'userIdentity': {
                    'type': 'AssumedRole',
                    'arn': 'foo/awslambda'
                }
            }
        }
        self.assertEqual(
            utils.get_aws_username_from_event(Mock(), evt),
            None
        )

    def test_get_username_assumed_role_colons(self):
        evt = {
            'detail': {
                'userIdentity': {
                    'type': 'AssumedRole',
                    'arn': 'foo/bar:baz:blam'
                }
            }
        }
        self.assertEqual(
            utils.get_aws_username_from_event(Mock(), evt),
            'baz:blam'
        )

    def test_get_username_iam(self):
        evt = {
            'detail': {
                'userIdentity': {
                    'type': 'IAMUser',
                    'userName': 'bar'
                }
            }
        }
        self.assertEqual(
            utils.get_aws_username_from_event(Mock(), evt),
            'bar'
        )

    def test_get_username_root(self):
        evt = {
            'detail': {
                'userIdentity': {
                    'type': 'Root'
                }
            }
        }
        self.assertEqual(
            utils.get_aws_username_from_event(Mock(), evt),
            None
        )

    def test_get_username_principalColon(self):
        evt = {
            'detail': {
                'userIdentity': {
                    'type': 'foo',
                    'principalId': 'bar:baz'
                }
            }
        }
        self.assertEqual(
            utils.get_aws_username_from_event(Mock(), evt),
            'baz'
        )

    def test_get_username_principal(self):
        evt = {
            'detail': {
                'userIdentity': {
                    'type': 'foo',
                    'principalId': 'blam'
                }
            }
        }
        self.assertEqual(
            utils.get_aws_username_from_event(Mock(), evt),
            'blam'
        )


class ProviderSelector(unittest.TestCase):

    def test_get_providers(self):
        self.assertEqual(utils.get_provider({'queue_url': 'asq://'}), utils.Providers.Azure)
        self.assertEqual(utils.get_provider({'queue_url': 'sqs://'}), utils.Providers.AWS)


class DecryptTests(unittest.TestCase):

    @patch('c7n_mailer.utils.kms_decrypt')
    def test_kms_decrypt(self, kms_decrypt_mock):
        utils.decrypt({'queue_url': 'aws', 'test': 'test'}, Mock(), Mock(), 'test')
        kms_decrypt_mock.assert_called_once()

    @patch('c7n_mailer.azure_mailer.utils.azure_decrypt')
    def test_azure_decrypt(self, azure_decrypt_mock):
        utils.decrypt({'queue_url': 'asq://', 'test': 'test'}, Mock(), Mock(), 'test')
        azure_decrypt_mock.assert_called_once()

    def test_decrypt_none(self):
        self.assertEqual(utils.decrypt({'queue_url': 'aws'}, Mock(), Mock(), 'test'), None)
        self.assertEqual(utils.decrypt({'queue_url': 'asq://'}, Mock(), Mock(), 'test'), None)
