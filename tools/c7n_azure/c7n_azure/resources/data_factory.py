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

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources


@resources.register('datafactory')
class DataFactory(ArmResourceManager):
    """Data Factory Resource

    :example:

    This policy will find all Data Factories with 10 or more failures in pipeline
    runs over the last 72 hours

    .. code-block:: yaml

        policies:
          - name: datafactory-dropping-messages
            resource: azure.datafactory
            filters:
              - type: metric
                metric: PipelineFailedRuns
                op: ge
                aggregation: total
                threshold: 10
                timeframe: 72

    """
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Analytics']

        service = 'azure.mgmt.datafactory'
        client = 'DataFactoryManagementClient'
        enum_spec = ('factories', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.DataFactory/factories'
