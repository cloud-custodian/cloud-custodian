# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
import pytest
import os
import json
from botocore.exceptions import ClientError
from .common import BaseTest
from c7n.exceptions import PolicyValidationError

from pytest_terraform import terraform


@pytest.mark.skiplive
@terraform('eks_nodegroup_delete')
def test_eks_nodegroup_delete(test, eks_nodegroup_delete):
    aws_region = 'eu-central-1'
    session_factory = test.replay_flight_data('test_eks_nodegroup_delete', region=aws_region)

    client = session_factory().client('eks')
    eks_cluster_name = eks_nodegroup_delete['aws_eks_node_group.deleted_example.cluster_name']
    eks_nodegroup_name = eks_nodegroup_delete['aws_eks_node_group.deleted_example.node_group_name']

    p = test.load_policy(
        {
            'name': 'eks-nodegroup-delete',
            'resource': 'eks-nodegroup',
            'filters': [
                {'clusterName': eks_cluster_name},
                {'and': [
                    {'tag:Name': eks_nodegroup_name},
                    {'tag:ClusterName': eks_cluster_name},
                ]},
            ],
            'actions': [{'type': 'delete'}],
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    test.assertEqual(len(resources), 1)

    nodegroup = client.describe_nodegroup(
        clusterName=eks_cluster_name,
        nodegroupName=eks_nodegroup_name
    )['nodegroup']
    test.assertEqual(nodegroup['status'], 'DELETING')


class EKS(BaseTest):

    def test_config(self):
        factory = self.replay_flight_data('test_eks_config')
        p = self.load_policy(
            {"name": "eks", "source": "config", "resource": "eks"},
            session_factory=factory,
            config={'region': 'us-east-2'})
        resources = p.run()
        assert resources[0]['name'] == 'kapil-dev'

    def test_query_with_subnet_sg_filter(self):
        factory = self.replay_flight_data("test_eks_query")
        p = self.load_policy(
            {
                "name": "eks",
                "resource": "eks",
                "filters": [
                    {'type': 'subnet',
                     'key': 'tag:kubernetes.io/cluster/dev',
                     'value': 'shared'},
                    {'type': 'security-group',
                     'key': 'tag:App',
                     'value': 'eks'}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'dev')

    def test_update_config_schema_validation(self):
        with self.assertRaises(PolicyValidationError) as err:
            self.load_policy(
                {
                    "name": "update-eks-config",
                    "resource": "eks",
                    "actions": [{
                        "type": "update-config",
                        "unknownOption": True,
                    }],
                },
            )
        self.assertIn(
            "unknownOption",
            str(err.exception)
        )

    def test_update_config(self):
        factory = self.replay_flight_data('test_eks_update_config')
        p = self.load_policy({
            'name': 'eksupdate',
            'resource': 'eks',
            'filters': [
                {'name': 'devk8s'},
                {'resourcesVpcConfig.endpointPublicAccess': True}],
            'actions': [{
                'type': 'update-config',
                'resourcesVpcConfig': {
                    'endpointPublicAccess': False,
                    'endpointPrivateAccess': True
                }}]}, session_factory=factory, config={'region': 'us-east-2'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(10)
        client = factory().client('eks')
        info = client.describe_cluster(name='devk8s')['cluster']
        self.assertEqual(resources[0]['status'], 'ACTIVE')
        self.assertEqual(info['status'], 'UPDATING')

    def test_delete_eks(self):
        factory = self.replay_flight_data("test_eks_delete")
        p = self.load_policy(
            {
                "name": "eksdelete",
                "resource": "eks",
                "filters": [{"name": "dev"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("eks")
        cluster = client.describe_cluster(name='dev').get('cluster')
        self.assertEqual(cluster['status'], 'DELETING')

    def test_delete_eks_with_both(self):
        name = "test_f1"
        factory = self.replay_flight_data("test_eks_delete_with_both")
        client = factory().client("eks")
        nodegroupNames = client.list_nodegroups(clusterName=name)['nodegroups']
        self.assertEqual(len(nodegroupNames), 1)
        fargateProfileNames = client.list_fargate_profiles(
            clusterName=name)['fargateProfileNames']
        self.assertEqual(len(fargateProfileNames), 1)
        p = self.load_policy(
            {
                "name": "eks-delete",
                "resource": "eks",
                "filters": [{"name": name}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        nodegroupNames = client.list_nodegroups(clusterName=resources[0]['name'])['nodegroups']
        self.assertEqual(len(nodegroupNames), 0)
        fargateProfileNames = client.list_fargate_profiles(
            clusterName=resources[0]['name'])['fargateProfileNames']
        self.assertEqual(len(fargateProfileNames), 0)
        cluster = client.describe_cluster(name=name).get('cluster')
        self.assertEqual(cluster['status'], 'DELETING')

    def test_tag_and_remove_tag(self):
        factory = self.replay_flight_data('test_eks_tag_and_remove_tag')
        p = self.load_policy({
            'name': 'eks-tag-and-remove',
            'resource': 'aws.eks',
            'filters': [{'tag:Env': 'Dev'}],
            'actions': [
                {'type': 'tag', 'tags': {'App': 'Custodian'}},
                {'type': 'remove-tag', 'tags': ['Env']}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'devx')
        client = factory().client('eks')
        self.assertEqual(
            client.describe_cluster(
                name='devx')['cluster']['tags'],
            {'App': 'Custodian'})

    def test_kms_filter(self):
        factory = self.replay_flight_data('test_eks_kms_filter')
        kms = factory().client('kms')
        p = self.load_policy(
            {
                'name': 'test-eks-kms-filter',
                'resource': 'aws.eks',
                'filters': [
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': '^(alias/eks)',
                        'op': 'regex'
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        kmsKeyId = resources[0]['encryptionConfig'][0]['provider']['keyArn']
        aliases = kms.list_aliases(KeyId=kmsKeyId)
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/eks')

    def test_network_location_filter(self):
        factory = self.replay_flight_data("test_eks_network_location_filter")

        p = self.load_policy(
            {
                "name": "test_eks_network_location_filter",
                "resource": "eks",
                "filters": [
                    {
                        "type": "network-location",
                        "compare": ["resource", "security-group"],
                        "key": "tag:NetworkLocation",
                        "match": "equal"
                    }
                ]
            },
            session_factory=factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(
            matched["Tags"],
            [
                {
                    'Key': 'NetworkLocation',
                    'Value': 'Customer'
                }
            ]
        )

    def test_associate_encryption_config(self):
        factory = self.replay_flight_data("test_eks_associate_encryption_config")

        p = self.load_policy(
            {
                'name': 'test-eks-associate-encryption-config',
                'resource': 'aws.eks',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'encryptionConfig[].provider.keyArn',
                        'value': 'absent'
                    }
                ],
                'actions': [
                    {
                        'type': 'associate-encryption-config',
                        'encryptionConfig': [
                            {
                                'provider': {
                                    'keyArn': 'alias/eks'
                                },
                                'resources': [
                                    'secrets'
                                ]
                            }
                        ]
                    }
                ]
            },
            session_factory=factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(matched['status'], 'ACTIVE')
        update_json = os.path.join(self.placebo_dir, "test_eks_associate_encryption_config",
        "eks.AssociateEncryptionConfig_1.json")
        with open(update_json) as f:
            data = json.load(f)
        self.assertEqual(data['status_code'], 200)
        self.assertEqual(data['data']['update']['type'], 'AssociateEncryptionConfig')
        self.assertEqual(data['data']['update']['status'], 'InProgress')

    def test_associate_encryption_config_key_arn(self):
        factory = self.replay_flight_data("test_eks_associate_encryption_config_key_arn")

        p = self.load_policy(
            {
                'name': 'test-eks-associate-encryption-config',
                'resource': 'aws.eks',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'encryptionConfig[].provider.keyArn',
                        'value': 'absent'
                    }
                ],
                'actions': [
                    {
                        'type': 'associate-encryption-config',
                        'encryptionConfig': [
                            {
                                'provider': {
                                    'keyArn':
                                    'arn:aws:kms:us-east-1:644160558196:key/361001ad-9c5e-42cb-9a09-5de1e80e822f'
                                },
                                'resources': [
                                    'secrets'
                                ]
                            }
                        ]
                    }
                ]
            },
            session_factory=factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(matched['status'], 'ACTIVE')
        update_json = os.path.join(
            self.placebo_dir,
            "test_eks_associate_encryption_config_key_arn", "eks.AssociateEncryptionConfig_1.json"
        )
        with open(update_json) as f:
            data = json.load(f)
        self.assertEqual(data['status_code'], 200)
        self.assertEqual(data['data']['update']['type'], 'AssociateEncryptionConfig')
        self.assertEqual(data['data']['update']['status'], 'InProgress')

    def test_associate_encryption_config_invalid_kms(self):
        factory = self.replay_flight_data("test_eks_associate_encryption_config_invalid_kms")

        p = self.load_policy(
            {
                'name': 'test-eks-associate-encryption-config',
                'resource': 'aws.eks',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'encryptionConfig[].provider.keyArn',
                        'value': 'absent'
                    }
                ],
                'actions': [
                    {
                        'type': 'associate-encryption-config',
                        'encryptionConfig': [
                            {
                                'provider': {
                                    'keyArn': 'alias/eks_invalid_key'
                                },
                                'resources': [
                                    'secrets'
                                ]
                            }
                        ]
                    }
                ]
            },
            session_factory=factory
        )
        with self.assertRaises(ClientError) as error:
            resources = p.run()
            self.assertEqual(len(resources), 1)
        self.assertEqual(error.exception.response['Error']['Code'], 'NotFoundException')

    def test_associate_encryption_config_invalid_kms_key(self):
        factory = self.replay_flight_data("test_eks_associate_encryption_config_invalid_kms_key")

        p = self.load_policy(
            {
                'name': 'test-eks-associate-encryption-config',
                'resource': 'aws.eks',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'encryptionConfig[].provider.keyArn',
                        'value': 'absent'
                    }
                ],
                'actions': [
                    {
                        'type': 'associate-encryption-config',
                        'encryptionConfig': [
                            {
                                'provider': {
                                    'keyArn': 'arn:aws:kms:us-east-1:644160558196:key/123'
                                },
                                'resources': [
                                    'secrets'
                                ]
                            }
                        ]
                    }
                ]
            },
            session_factory=factory
        )
        with self.assertRaises(ClientError) as error:
            resources = p.run()
            self.assertEqual(len(resources), 1)
        self.assertEqual(error.exception.response['Error']['Code'], 'InvalidParameterException')
