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


@resources.register('cognitiveservice')
class CognitiveService(ArmResourceManager):
    """Cognitive Services Resource

    :example:
    This policy will find all Cognitive Service accounts with 1000 or more
    total errors over the 72 hours

    .. code-block:: yaml

        policies:
          - name: cogserv-many-failures
            resource: azure.cognitiveservice
            filters:
              - type: metric
                metric: TotalErrors
                op: ge
                aggregation: total
                threshold: 1000
                timeframe: 72

    """

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.cognitiveservices'
        client = 'CognitiveServicesManagementClient'
        enum_spec = ('accounts', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.CognitiveServices/accounts'
