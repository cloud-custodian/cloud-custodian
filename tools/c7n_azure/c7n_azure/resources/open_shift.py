# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('open-shift')
class OpenShiftService(ArmResourceManager):
    """Azure Red Hat Openshift Service Resource

    :example:

    Delete all open-shift clusters that did not provision successfully

    .. code-block:: yaml

        policies:
          - name: broken-open-shift
            resource: azure.open-shift
            filters:
              - type: value
                key: properties.provisioningState
                op: not-equal
                value_type: normalize
                value: succeeded
            actions:
              - type: delete

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute', 'Containers']
        service = 'azure.mgmt.redhatopenshift'
        client = 'AzureRedHatOpenShiftClient'
        enum_spec = ('open_shift_clusters', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.RedHatOpenShift/openShiftClusters'
