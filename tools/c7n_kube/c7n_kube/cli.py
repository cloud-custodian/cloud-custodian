# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import argparse
import logging
import os
import pkg_resources

import yaml

from c7n_kube.server import init

from c7n.config import Config
from c7n.loader import DirectoryLoader

log = logging.getLogger("custodian.k8s.cli")
logging.basicConfig(
    # TODO: make this configurable
    level=logging.INFO,
    format="%(asctime)s: %(name)s:%(levelname)s %(message)s",
)


TEMPLATE = {
    "apiVersion": "admissionregistration.k8s.io/v1",
    "kind": "MutatingWebhookConfiguration",
    "metadata": {
        "name": "c7n-admission",
        "labels": {
            "app.kubernetes.io/name": "c7n-kates",
            "app.kubernetes.io/instance": "c7n-kates",
            "app.kubernetes.io/version": pkg_resources.get_distribution("c7n_kube").version,
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
                    "operations": [],
                    "scope": "*",
                    "apiGroups": [],
                    "apiVersions": [],
                    "resources": [],
                }
            ],
            "admissionReviewVersions": ["v1", "v1beta1"],
            "clientConfig": {"url": "${ENDPOINT}"},
            "sideEffects": "None",
            "failurePolicy": "Fail",
        }
    ],
}


def _parser():
    parser = argparse.ArgumentParser(description="Cloud Custodian Admission Controller")
    parser.add_argument("--host", type=str, help="Listen host", default="127.0.0.1")
    parser.add_argument("--port", type=int, help="Listen port", nargs="?", default="8800")
    parser.add_argument("--policy-dir", type=str, required=True, help="policy directory")
    parser.add_argument(
        "--on-exception",
        type=str.lower,
        required=False,
        default="warn",
        choices=["warn", "deny"],
        help="warn or deny on policy exceptions",
    )
    parser.add_argument(
        "--endpoint",
        help="Endpoint for webhook, used for generating manfiest",
        required=True,
    )
    parser.add_argument(
        "--generate",
        default=False,
        action="store_true",
        help="Generate a k8s manifest for ValidatingWebhookConfiguration",
    )
    parser.add_argument("--cert", help="Path to TLS certifciate")
    parser.add_argument("--ca-cert", help="Path to the CA certificate")
    parser.add_argument("--cert-key", help="Path to the certificate's private key")
    return parser


def cli():
    """
    Cloud Custodian Admission Controller
    """
    parser = _parser()
    args = parser.parse_args()
    if args.generate:
        directory_loader = DirectoryLoader(Config.empty())
        policy_collection = directory_loader.load_directory(os.path.abspath(args.policy_dir))
        operations = []
        groups = []
        api_versions = []
        resources = []
        for p in policy_collection:
            execution_mode = p.get_execution_mode()
            # We only support `k8s-admission` policies for the admission
            # controller.
            if execution_mode.type != "k8s-admission":
                policy = execution_mode.policy
                type_ = execution_mode.type
                log.warning(
                    f"skipping policy {policy.name} with type {type_}, should be k8s-admission"
                )
                continue
            mvals = p.get_execution_mode().get_match_values()
            operations.extend(mvals["operations"])
            groups.append(mvals["group"])
            api_versions.append(mvals["apiVersions"])
            resources.extend(mvals["resources"])

        TEMPLATE["webhooks"][0]["rules"][0]["operations"] = sorted(list(set(operations)))
        TEMPLATE["webhooks"][0]["rules"][0]["apiGroups"] = sorted(list(set(groups)))
        TEMPLATE["webhooks"][0]["rules"][0]["apiVersions"] = sorted(list(set(api_versions)))
        TEMPLATE["webhooks"][0]["rules"][0]["resources"] = sorted(list(set(resources)))

        if args.endpoint:
            TEMPLATE["webhooks"][0]["clientConfig"]["url"] = args.endpoint

        print(yaml.dump(TEMPLATE))
    else:
        init(
            args.host,
            args.port,
            args.policy_dir,
            args.on_exception,
            cert_path=args.cert,
            cert_key_path=args.cert_key,
            ca_cert_path=args.ca_cert,
        )


if __name__ == "__main__":
    cli()
