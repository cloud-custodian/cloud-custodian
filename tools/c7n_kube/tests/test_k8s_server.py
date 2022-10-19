# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import socket
import tempfile
import threading
import time

import requests

from unittest.mock import patch, MagicMock

from c7n_kube.server import \
    AdmissionControllerServer, AdmissionControllerHandler, init

from common_kube import KubeTest


class TestAdmissionControllerServer(AdmissionControllerServer):
    def __init__(self, bind_and_activate=False, *args, **kwargs):
        super().__init__(
            bind_and_activate=bind_and_activate, *args, **kwargs)


class TestServer(KubeTest):

    def find_port(self):
        sock = socket.socket()
        sock.bind(('', 0))
        _, port = sock.getsockname()
        return port

    def _server(self, policies, on_exception='warn'):
        port = self.find_port()
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(policies, f)
            server = TestAdmissionControllerServer(
                server_address=('localhost', port),
                RequestHandlerClass=AdmissionControllerHandler,
                policy_dir=temp_dir,
                bind_and_activate=True,
                on_exception=on_exception,
            )
            server_thread = threading.Thread(target=server.handle_request)
            server_thread.start()
            time.sleep(1)
        return server, port

    def test_server_load_non_k8s_policies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test', 'resource': 's3'}]}, f
                )
            with open(f"{temp_dir}/policy2.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test2', 'resource': 'ec2'}]}, f
                )
            with open(f"{temp_dir}/policy3.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test3', 'resource': 'ebs'}]}, f
                )
            server = TestAdmissionControllerServer(
                server_address=('localhost', 8080),
                RequestHandlerClass=AdmissionControllerHandler,
                policy_dir=temp_dir
            )

            self.assertEqual(len(server.policy_collection.policies), 0)

    def test_server_load_k8s_policies_no_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test', 'resource': 'k8s.pod'}]}, f
                )
            with open(f"{temp_dir}/policy2.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test2', 'resource': 'k8s.deployment'}]}, f
                )
            with open(f"{temp_dir}/policy3.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test3', 'resource': 'k8s.service'}]}, f
                )
            server = TestAdmissionControllerServer(
                server_address=('localhost', 8082),
                RequestHandlerClass=AdmissionControllerHandler,
                policy_dir=temp_dir
            )

            self.assertEqual(len(server.policy_collection.policies), 0)

    def test_server_load_k8s_policies_proper_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(
                    {
                        "policies": [
                            {
                                'name': 'test',
                                'resource': 'k8s.pod',
                                'mode': {
                                    'type': 'k8s-admission',
                                    'operations': ['CREATE']
                                }
                            }
                        ]
                    }, f
                )
            with open(f"{temp_dir}/policy2.yaml", "w+") as f:
                json.dump(
                    {
                        "policies": [
                            {
                                'name': 'test2',
                                'resource': 'k8s.deployment',
                                'mode': {
                                    'type': 'k8s-admission',
                                    'operations': ['CREATE']
                                }
                            }
                        ]
                    }, f
                )
            with open(f"{temp_dir}/policy3.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test3', 'resource': 'k8s.service'}]}, f
                )
            server = TestAdmissionControllerServer(
                server_address=('localhost', 8080),
                RequestHandlerClass=AdmissionControllerHandler,
                policy_dir=temp_dir
            )

            # we should only have 2 policies here since there's only 2 policies with the right mode
            self.assertEqual(len(server.policy_collection.policies), 2)

    def test_server_handle_get_empty_policies(self):
        policies = {
            'policies': []
        }
        server, port = self._server(policies)
        res = requests.get(f'http://localhost:{port}')
        self.assertEqual(res.json(), [])
        self.assertEqual(res.status_code, 200)

    def test_server_handle_get_policies(self):
        policies = {
            'policies': [
                {
                    'name': 'test-validator',
                    'resource': 'k8s.pod',
                    'mode': {
                        'type': 'k8s-admission',
                        'on-match': 'deny',
                        'operations': [
                            'CREATE',
                        ]
                    }
                }
            ]
        }
        server, port = self._server(policies)
        res = requests.get(f'http://localhost:{port}')
        self.assertEqual(res.json(), policies['policies'])
        self.assertEqual(res.status_code, 200)

    def test_server_handle_post_no_policies(self):
        policies = {
            'policies': []
        }
        server, port = self._server(policies)
        event = self.get_event('create_pod')
        res = requests.post(f'http://localhost:{port}', json=event)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            {
                'apiVersion': 'admission.k8s.io/v1',
                'kind': 'AdmissionReview',
                'response': {
                    'allowed': True,
                    'uid': '662c3df2-ade6-4165-b395-770857bc17b7',
                    'warnings': [],
                    'status': {
                        'code': 200,
                        'message': 'OK'
                    }
                }
            },
            res.json()
        )

    def test_server_handle_post_policies_deny_on_match(self):
        policies = {
            'policies': [
                {
                    'name': 'test-validator',
                    'resource': 'k8s.pod',
                    'mode': {
                        'type': 'k8s-admission',
                        'on-match': 'deny',
                        'operations': [
                            'CREATE',
                        ]
                    }
                }
            ]
        }
        server, port = self._server(policies)
        event = self.get_event('create_pod')
        res = requests.post(f'http://localhost:{port}', json=event)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()['response']['allowed'])

    def test_server_handle_post_policies_allow_on_match(self):
        policies = {
            'policies': [
                {
                    'name': 'test-validator',
                    'resource': 'k8s.pod',
                    'mode': {
                        'type': 'k8s-admission',
                        'on-match': 'allow',
                        'operations': [
                            'CREATE',
                        ]
                    }
                }
            ]
        }
        server, port = self._server(policies)
        event = self.get_event('create_pod')
        res = requests.post(f'http://localhost:{port}', json=event)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['response']['allowed'])

    def test_server_handle_post_policies_deny_on_match_multiple(self):
        policies = {
            'policies': [
                {
                    'name': 'test-validator-deployment',
                    'resource': 'k8s.deployment',
                    'description': 'description deployment',
                    'mode': {
                        'type': 'k8s-admission',
                        'on-match': 'deny',
                        'operations': [
                            'CREATE',
                        ]
                    }
                },
                {
                    'name': 'test-validator',
                    'resource': 'k8s.pod',
                    'description': 'description 1',
                    'mode': {
                        'type': 'k8s-admission',
                        'on-match': 'deny',
                        'operations': [
                            'CREATE',
                        ]
                    }
                },
                {
                    'name': 'test-validator-2',
                    'description': 'description 2',
                    'resource': 'k8s.pod',
                    'mode': {
                        'type': 'k8s-admission',
                        'on-match': 'deny',
                        'operations': [
                            'CREATE',
                        ]
                    }
                }
            ]
        }
        server, port = self._server(policies)
        event = self.get_event('create_pod')
        res = requests.post(f'http://localhost:{port}', json=event)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()['response']['allowed'])
        failures = json.loads(
            res.json()['response']['status']['message'].split(':', 1)[-1]
        )
        self.assertEqual(len(failures), 2)
        self.assertEqual(failures[0], {'name': 'test-validator', 'description': 'description 1'})
        self.assertEqual(failures[1], {'name': 'test-validator-2', 'description': 'description 2'})

    def test_server_onmatch_warn(self):
        policies = {
            'policies': [
                {
                    'name': 'test-validator-pod',
                    'resource': 'k8s.pod',
                    'description': 'description deployment',
                    'mode': {
                        'type': 'k8s-admission',
                        'on-match': 'warn',
                        'operations': [
                            'CREATE',
                        ]
                    }
                },
            ]
        }
        server, port = self._server(policies)
        event = self.get_event('create_pod')
        res = requests.post(f'http://localhost:{port}', json=event)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['response']['allowed'])
        self.assertEqual(
            res.json()['response']['warnings'],
            ['test-validator-pod:description deployment']
        )

    def test_server_init(self):
        with patch('c7n_kube.server.AdmissionControllerServer') as patched:
            port = self.find_port()
            init(port, 'policies', serve_forever=False)
            patched.assert_called_once()
            patched.assert_called_with(
                server_address=('0.0.0.0', port),
                RequestHandlerClass=AdmissionControllerHandler,
                policy_dir='policies',
                on_exception='warn'
            )
            patched.return_value.serve_forever.assert_called_once()

    def test_server_bad_post(self):
        policies = {'policies': []}
        server, port = self._server(policies)
        res = requests.post(f'http://localhost:{port}', data='bad data')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {'error': 'Expecting value: line 1 column 1 (char 0)'})

    def test_server_bad_policy_execution_warn(self):
        policies = {
            'policies': [
                {
                    'name': 'test-validator-pod',
                    'resource': 'k8s.pod',
                    'description': 'description deployment',
                    'mode': {
                        'type': 'k8s-admission',
                        'on-match': 'warn',
                        'operations': [
                            'CREATE',
                        ]
                    }
                },
            ]
        }
        server, port = self._server(policies)

        server.policy_collection = MagicMock()
        server.policy_collection.policies = []

        mock_policy_1 = MagicMock()
        mock_policy_1.name = 'test-validator-pod'
        mock_policy_1.push.side_effect = Exception('foo')

        mock_policy_2 = MagicMock()
        mock_policy_2.name = 'test-validator-pod-2'
        mock_policy_2.push.side_effect = Exception('bar')

        server.policy_collection.policies.append(mock_policy_1)
        server.policy_collection.policies.append(mock_policy_2)

        event = self.get_event('create_pod')
        res = requests.post(f'http://localhost:{port}', json=event)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json()['response']['warnings'],
            [
                'test-validator-pod:Error in executing policy: foo',
                'test-validator-pod-2:Error in executing policy: bar'
            ]
        )

    def test_server_bad_policy_execution_deny(self):
        policies = {
            'policies': [
                {
                    'name': 'test-validator-pod',
                    'resource': 'k8s.pod',
                    'description': 'description deployment',
                    'mode': {
                        'type': 'k8s-admission',
                        'on-match': 'warn',
                        'operations': [
                            'CREATE',
                        ]
                    }
                },
            ]
        }
        server, port = self._server(policies, on_exception='deny')

        server.policy_collection = MagicMock()
        server.policy_collection.policies = []

        mock_policy_1 = MagicMock()
        mock_policy_1.name = 'test-validator-pod'
        mock_policy_1.push.side_effect = Exception('foo')

        mock_policy_2 = MagicMock()
        mock_policy_2.name = 'test-validator-pod-2'
        mock_policy_2.push.side_effect = Exception('bar')

        server.policy_collection.policies.append(mock_policy_1)
        server.policy_collection.policies.append(mock_policy_2)

        event = self.get_event('create_pod')
        res = requests.post(f'http://localhost:{port}', json=event)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()['response']['allowed'])
        failures = json.loads(
            res.json()['response']['status']['message'].split(':', 1)[-1]
        )
        self.assertEqual(
            failures,
            [
                {"name": "test-validator-pod", "description": "Error in executing policy: foo"},
                {"name": "test-validator-pod-2", "description": "Error in executing policy: bar"}
            ]
        )
