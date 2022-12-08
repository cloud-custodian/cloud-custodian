# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_kube.actions.core import DeleteResource, PatchResource
from c7n_kube.actions.labels import LabelAction
from c7n_kube.provider import resources as kube_resources

SHARED_ACTIONS = (DeleteResource, LabelAction, PatchResource)


for action in SHARED_ACTIONS:
    kube_resources.subscribe(action.register_resources)
