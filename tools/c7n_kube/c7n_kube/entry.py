# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

from c7n_kube.resources.core import (
    configmap,
    namespace,
    node,
    pod,
    replicationcontroller,
    secret,
    service,
    serviceaccount,
    volume)

from c7n_kube.resources.apps import (
    daemonset,
    deployment,
    replicaset,
    statefulset)

log = logging.getLogger('custodian.k8s')

ALL = [
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
    statefulset]


def initialize_kube():
    """kubernetes entry point
    """
