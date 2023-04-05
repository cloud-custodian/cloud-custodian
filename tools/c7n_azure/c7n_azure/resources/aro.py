# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('aro')
class AROService(ArmResourceManager):
    """Azure Red Hat Openshift Service Resource

    :example:

    Returns all aro clusters that did not provision successfully

    .. code-block:: yaml

        policies:
          - name: broken-aro
            resource: azure.aro
            filters:
              - type: value
                key: properties.provisioningState
                op: not-equal
                value_type: normalize
                value: succeeded

    """

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.redhatopenshift'
        client = 'AzureRedHatOpenShiftClient'
        enum_spec = ('open_shift_clusters', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'properties.version',
            'properties.masterProfile',
            'properties.workerProfiles[][name, count]'
        )
        resource_type = 'Microsoft.RedHatOpenShift/openShiftClusters'
