# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.actions.base import AzureBaseAction
from c7n.utils import type_schema


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
            'properties.clusterDefinition.kind',
            'properties.tier'
        )
        resource_type = 'Microsoft.HDInsight/clusters'


@Hdinsight.action_registry.register('resize')
class Resize(AzureBaseAction):

    """
    Action to scale HDInsight Clusters

    :example:

    This policy will resize the cluster to 4 nodes

    .. code-block:: yaml

        policies:
          - name: resize-hdinsight
            resource: azure.hdinsight
            filters:
              - type: value
                key: name
                value: cctesthdinsight
            actions:
              - type: resize
                count: 4

    """

    schema = type_schema(
        'resize',
        required=['count'],
        **{
            'count': {'type': 'integer', 'minimum': 1}
        })

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, cluster):
        self.client.clusters.resize(
            cluster['resourceGroup'],
            cluster['name'],
            target_instance_count=self.data['count']
        )
