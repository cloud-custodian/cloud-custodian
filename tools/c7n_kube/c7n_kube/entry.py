# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

import c7n_kube.actions.shared  # noqa

from c7n_kube.resources.core import (
    configmap,
    namespace,
    node,
    pod,
    replicationcontroller,
    secret,
    service,
    serviceaccount,
    volume,
)

from c7n_kube.resources.apps import daemonset, deployment, replicaset, statefulset

from c7n_kube.resources import crd

import c7n_kube.policy  # noqa

log = logging.getLogger("custodian.k8s")

ALL = [
    crd,
    configmap,
    deployment,
    namespace,
    node,
    pod,
    replicationcontroller,
    secret,
    service,
    serviceaccount,
    volume,
    daemonset,
    replicaset,
    statefulset,
]


def initialize_kube():
    """kubernetes entry point"""
