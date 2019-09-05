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


@resources.register('hdinsight')
class Hdinsight(ArmResourceManager):
    """HDInsight Resource

    :example:

    Finds all Hadoop HDInsight Clusters

    .. code-block:: yaml

        policies:
          - name: hdinsight-policy
            resource: azure.hdinsight
            filters:
              - type: value
                key: properties.clusterDefinition.kind
                value_type: normalize
                value: hadoop

    :example:

    Finds all HDInsight Clusters with 3 worker nodes

    .. code-block:: yaml

        policies:
          - name: hdinsight-policy
            resource: azure.hdinsight
            filters:
              - type: value
                key: properties.computeProfile.roles[?name=='workernode'].targetInstanceCount | [0]
                op: eq
                value_type: integer
                value: 3

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Analytics']

        service = 'azure.mgmt.hdinsight'
        client = 'HDInsightManagementClient'
        enum_spec = ('clusters', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.clusterDefinition.kind'
        )
        resource_type = 'Microsoft.HDInsight/clusters'
