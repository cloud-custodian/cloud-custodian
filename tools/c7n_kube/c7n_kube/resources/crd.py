# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_kube.query import CustomResourceQueryManager, CustomTypeInfo
from c7n_kube.provider import resources


@resources.register("custom-namespaced-resource")
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


@resources.register("custom-cluster-resource")
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
