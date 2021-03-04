# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

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
        resource_type = 'Microsoft.DataFactory/factories'
