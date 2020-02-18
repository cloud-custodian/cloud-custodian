# Copyright 2019 Microsoft Corporation
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

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('search')
class SearchService(ArmResourceManager):
    """Azure Search Service Resource

    :example:

    Returns all Search services on the Basic SKU

    .. code-block:: yaml

        policies:
          - name: basic-search
            resource: azure.search
            filters:
              - type: value
                key: sku.name
                op: equal
                value: Basic

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']

        service = 'azure.mgmt.search'
        client = 'SearchManagementClient'
        enum_spec = ('services', 'list_by_subscription', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name'
        )
        resource_type = 'Microsoft.Search/searchServices'
