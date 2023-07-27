# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
import pkg_resources
import tempfile

from common_kube import KubeTest

from unittest.mock import patch, MagicMock

from c7n_kube.cli import _parser, cli


class TestK8sCli(KubeTest):
    def test_parser(self):
        parser = _parser()
        self.assertTrue(isinstance(parser, argparse.ArgumentParser))

    @patch("c7n_kube.cli._parser")
    def test_cli_generate(self, patched_parser):
        policies = {
            "policies": [
                {
                    "name": "test-validator",
                    "resource": "k8s.pod",
                    "mode": {
                        "type": "k8s-admission",
                        "on-match": "allow",
                        "operations": ["CREATE", "DELETE"],
                    },
                },
                {
                    "name": "no-custom-resource-for-you",
                    "resource": "k8s.custom-namespaced-resource",
                    "query": [
                        {
                            "plural": "policyreports",
                            "group": "wgpolicyk8s.io",
                            "version": "v1alpha2",
                        }
                    ],
                    "mode": {
                        "type": "k8s-admission",
                        "on-match": "deny",
                        "operations": ["CREATE"],
                    },
                },
            ]
        }

        version = pkg_resources.get_distribution("c7n_kube").version

        expected = {
            "apiVersion": "admissionregistration.k8s.io/v1",
            "kind": "MutatingWebhookConfiguration",
            "metadata": {
                "name": "c7n-admission",
                "labels": {
                    "app.kubernetes.io/name": "c7n-kates",
                    "app.kubernetes.io/instance": "c7n-kates",
                    "app.kubernetes.io/version": version,
                    "app.kubernetes.io/component": "AdmissionController",
                    "app.kubernetes.io/part-of": "c7n_kube",
                    "app.kubernetes.io/managed-by": "c7n",
                },
            },
            "webhooks": [
                {
                    "name": "admission.cloudcustodian.io",
                    "rules": [
                        {
                            "operations": ["CREATE", "DELETE"],
                            "scope": "*",
                            "apiGroups": ["", "wgpolicyk8s.io"],
                            "apiVersions": ["v1", "v1alpha2"],
                            "resources": ["pods", "policyreports"],
                        }
                    ],
                    "admissionReviewVersions": ["v1", "v1beta1"],
                    "clientConfig": {"url": "https://example.com"},
                    "sideEffects": "None",
                    "failurePolicy": "Fail",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(policies, f)
            patched_args = MagicMock()
            patched_args.generate = True
            patched_args.policy_dir = temp_dir
            patched_args.endpoint = "https://example.com"
            patched_parser.return_value.parse_args.return_value = patched_args
            with patch("c7n_kube.cli.yaml") as patched_yaml:
                cli()
                patched_yaml.dump.assert_called_once()
                patched_yaml.dump.assert_called_with(expected)

    @patch("c7n_kube.cli._parser")
    @patch("c7n_kube.cli.init")
    def test_cli_server(self, patched_init, patched_parser):
        patched_args = MagicMock()
        patched_args.port = 9000
        patched_args.generate = False
        patched_args.policy_dir = "policies"
        patched_args.on_exception = "warn"
        patched_args.cert = None
        patched_args.cert_key = None
        patched_args.ca_cert = None
        patched_args.host = "localhost"
        patched_parser.return_value.parse_args.return_value = patched_args
        cli()
        patched_init.assert_called_once_with(
            "localhost",
            9000,
            "policies",
            "warn",
            cert_path=None,
            cert_key_path=None,
            ca_cert_path=None,
        )
