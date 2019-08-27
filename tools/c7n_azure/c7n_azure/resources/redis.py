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

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('redis')
class Redis(ArmResourceManager):
    """Redis Resource

    :example:

    This policy will find all Redis caches with more than 1000 cache misses in the last 72 hours

    .. code-block:: yaml

        policies:
          - name: redis-cache-misses
            resource: azure.redis
            filters:
              - type: metric
                metric: cachemisses
                op: ge
                aggregation: count
                threshold: 1000
                timeframe: 72

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.redis'
        client = 'RedisManagementClient'
        enum_spec = ('redis', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Cache/Redis'
