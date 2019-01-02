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

from c7n_kube.actions import MethodAction
from c7n.utils import type_schema

log = logging.getLogger('custodian.k8s.labels')


class LabelResource(MethodAction):
    """
    label a k8s resource
    """

    schema = type_schema(
        'label',
        labels={'type': 'object'}
    )

    def process_resource_set(self, client, model, resources):
        op_name = self.method_spec['op']
        body = {'metadata': {'labels': self.data.get('labels', {})}}
        for r in resources:
            r = getattr(client, op_name)(r['metadata']['name'], body)


class LabelNamespacedResource(MethodAction):
    """
    label a k8s namespaced resource
    """

    schema = type_schema(
        'label',
        labels={'type': 'object'}
    )

    def process_resource_set(self, client, model, resources):
        op_name = self.method_spec['op']
        body = {'metadata': {'labels': self.data.get('labels', {})}}
        for r in resources:
            r = getattr(client, op_name)(r['metadata']['name'], r['metadata']['namespace'], body)
