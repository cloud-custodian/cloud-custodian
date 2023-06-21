# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.query import ChildResourceManager, ChildTypeInfo
from c7n_azure.utils import ResourceIdParser
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('spring-app')
class SpringApp(ChildResourceManager):
    """Azure Spring Apps Resource

    :example:

    Returns Spring Apps resources

    .. code-block:: yaml

         policies:
          - name: basic-spring-apps
            resource: azure.spring-app

    """

    class resource_type(ChildTypeInfo):
        doc_groups = ['Compute']

        service = 'azure.mgmt.appplatform'
        client = 'AppPlatformManagementClient'
        enum_spec = ('apps', 'list', None)
        parent_manager_name = 'spring-service-instance'

        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': ResourceIdParser.get_resource_group(parent_resource['id']),
                'service_name': parent_resource['name']
            }


@resources.register('spring-service-instance')
class SpringServiceInstance(ArmResourceManager):
    """Azure Spring Service Instance Resource

    :example:

    Returns Spring Service Instance resources

    .. code-block:: yaml

         policies:
          - name: basic-spring-service-instance
            resource: azure.spring-service-instance

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute']

        service = 'azure.mgmt.appplatform'
        client = 'AppPlatformManagementClient'
        enum_spec = ('services', 'list_by_subscription', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.AppPlatform/Spring'
