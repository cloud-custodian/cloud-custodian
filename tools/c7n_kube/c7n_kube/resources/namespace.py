# Copyright 2017-2018 Capital One Services, LLC
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
#
from c7n.utils import type_schema
from c7n_kube.actions import MethodAction
from c7n_kube.labels import LabelResource
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources

from kubernetes.client import V1DeleteOptions


@resources.register('namespace')
class Namespace(QueryResourceManager):
    class resource_type(TypeInfo):
        group = 'Core'
        version = 'V1'
        enum_spec = ('list_namespace', 'items', None)


@Namespace.action_registry.register('delete')
class Delete(MethodAction):
    """
    Deletes a Namespace

    .. code-block:: yaml
      policies:
        - name: delete-namespace
          resource: kube.namespace
          filters:
            - 'metadata.name': 'test-namespace'
          actions:
            - delete
    """
    schema = type_schema('delete')
    method_spec = {'op': 'delete_namespace'}

    def process_resource_set(self, client, model, resources):
        op_name = self.method_spec['op']
        for r in resources:
            getattr(client, op_name)(r['metadata']['name'], V1DeleteOptions())


@Namespace.action_registry.register('label')
class LabelNamespace(LabelResource):
    """
    Labels a Namespace

    .. code-block:: yaml
      policies:
        - name: label-namespace
          resource: kube.namespace
          filters:
            - 'metadata.name': 'test-namespace'
          actions:
            - type: label
              labels:
                label1: value1
                label2: value2

    To remove a label from a namespace, provide the label with the value ``null``

    .. code-block:: yaml
      policies:
        - name: remove-label-from-namespace
          resource: kube.namespace
          filters:
            - 'metadata.labels.label1': present
          actions:
            - type: label
              labels:
                label1: null

    """

    permissions = ('PatchNamespace',)
    method_spec = {'op': 'patch_namespace'}
