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

import c7n_kube.resources.configmap
import c7n_kube.resources.daemonset
import c7n_kube.resources.namespace
import c7n_kube.resources.node
import c7n_kube.resources.pod
import c7n_kube.resources.replicationcontroller
import c7n_kube.resources.secret
import c7n_kube.resources.service
import c7n_kube.resources.serviceaccount
import c7n_kube.resources.statefulset
import c7n_kube.resources.volume # NOQA

log = logging.getLogger('custodian.k8s')


def initialize_kube():
    """kubernetes entry point
    """
