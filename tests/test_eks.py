# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
from .common import BaseTest


class EKS(BaseTest):

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
