# Copyright 2019 Capital One Services, LLC
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

from c7n_kube.query import CustomResourceQueryManager, CustomTypeInfo
from c7n_kube.provider import resources


@resources.register('custom-namespaced-resource')
class CustomNamespacedResourceDefinition(CustomResourceQueryManager):
    """
    Query Custom Resources

    Custom resources require query to be defined with the group,
    version, and plural values from the resource definition

    policies:
      - name: custom-resource
        resource: k8s.custom-namespaced-resource
        query:
          - group: stable.example.com
            version: v1
            plural: crontabs
    """
    class resource_type(CustomTypeInfo):
        delete = "delete_namespaced_custom_object"
        patch = "patch_namespaced_custom_object"


@resources.register('custom-cluster-resource')
class CustomResourceDefinition(CustomResourceQueryManager):
    """
    Query Custom Resources

    Custom resources require query to be defined with the group,
    version, and plural values from the resource definition

    policies:
      - name: custom-resource
        resource: k8s.custom-cluster-resource
        query:
          - group: stable.example.com
            version: v1
            plural: crontabs
    """
    class resource_type(CustomTypeInfo):
        namespaced = False
        delete = "delete_cluster_custom_object"
        patch = "patch_cluster_custom_object"
