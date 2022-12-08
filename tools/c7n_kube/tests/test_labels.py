# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from common_kube import KubeTest


class TestLabelAction(KubeTest):
    def test_label_action(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                'name': 'label-namespace',
                'resource': 'k8s.namespace',
                'filters': [
                    {'metadata.labels': None},
                    {'metadata.name': 'test'}
                ],
                'actions': [
                    {
                        'type': 'label',
                        'labels': {'test': 'value'}
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertTrue(resources)
        client = factory().client(group='Core', version='V1')
        resources = client.list_namespace().to_dict()['items']
        test_namespace = [r for r in resources if r['metadata']['name'] == 'test']
        self.assertEqual(len(test_namespace), 1)
        labels = test_namespace[0]['metadata']['labels']
        self.assertEqual(labels, {'test': 'value'})

    def test_namespaced_label_action(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                'name': 'label-service',
                'resource': 'k8s.service',
                'filters': [
                    {'metadata.labels.test': 'absent'},
                    {'metadata.name': 'hello-node'}
                ],
                'actions': [
                    {
                        'type': 'label',
                        'labels': {'test': 'value'}
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertTrue(resources)
        client = factory().client(group='Core', version='V1')
        resources = client.list_service_for_all_namespaces().to_dict()['items']
        test_namespace = [r for r in resources if r['metadata']['name'] == 'hello-node']
        self.assertEqual(len(test_namespace), 1)
        labels = test_namespace[0]['metadata']['labels']
        self.assertTrue('test' in labels.keys())
        self.assertEqual(labels['test'], 'value')
