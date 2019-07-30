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


@resources.register('datalake')
class DataLakeStore(ArmResourceManager):
    """Data Lake Resource

    :example:

    This policy will find all Datalake Stores with one million or more
    write requests in the last 72 hours

    .. code-block:: yaml

        policies:
          - name: datalake-busy
            resource: azure.datalake
            filters:
              - type: metric
                metric: WriteRequests
                op: ge
                aggregation: total
                threshold: 1000000
                timeframe: 72

    """
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Storage']

        service = 'azure.mgmt.datalake.store'
        client = 'DataLakeStoreAccountManagementClient'
        enum_spec = ('accounts', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.DataLakeStore/accounts'
