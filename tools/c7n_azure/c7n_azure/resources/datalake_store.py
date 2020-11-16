# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

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
        resource_type = 'Microsoft.DataLakeStore/accounts'
