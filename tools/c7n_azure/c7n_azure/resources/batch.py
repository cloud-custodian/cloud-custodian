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


@resources.register('batch')
class Batch(ArmResourceManager):
    """Batch Resource

    :example:

    This set of policies will find all Azure Batch services that have more than 100 cores
    as the limit for the dedicated core quota.

    .. code-block:: yaml

        policies:
          - name: find-batch-with-high-dedicated-cores
            resource: azure.batch
            filters:
              - type: value
                key: properties.dedicatedCoreQuota
                op: gt
                value: 100

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute']

        service = 'azure.mgmt.batch'
        client = 'BatchManagementClient'
        enum_spec = ('batch_account', 'list', None)
        resource_type = 'Microsoft.Batch/batchAccounts'
