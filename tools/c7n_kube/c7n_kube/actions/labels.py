# Copyright 2018-2019 Capital One Services, LLC
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

from c7n_kube.actions.core import PatchAction
from c7n.utils import type_schema
log = logging.getLogger('custodian.k8s.labels')


class LabelAction(PatchAction):
    """
    Labels a resource

    .. code-block:: yaml
      policies:
        - name: label-{resource}
          resource: k8s.{resource}
          filters:
            - 'metadata.name': 'name'
          actions:
            - type: label
              labels:
                label1: value1
                label2: value2

    To remove a label from a resource, provide the label with the value ``null``

    .. code-block:: yaml
      policies:
        - name: remove-label-from-{resource}
          resource: k8s.{resource}
          filters:
            - 'metadata.labels.label1': present
          actions:
            - type: label
              labels:
                label1: null

    """

    schema = type_schema(
        'label',
        labels={'type': 'object'}
    )

    def process_resource_set(self, client, resources):
        body = {'metadata': {'labels': self.data.get('labels', {})}}
        patch_args = {'body': body}
        self.patch_resources(client, resources, **patch_args)

    @classmethod
    def register_resources(klass, registry, resource_class):
        model = resource_class.resource_type
        if hasattr(model, 'patch') and hasattr(model, 'namespaced'):
            resource_class.action_registry.register('label', klass)
