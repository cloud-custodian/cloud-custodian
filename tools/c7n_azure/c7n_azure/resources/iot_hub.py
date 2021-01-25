# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources


@resources.register('iothub')
class IoTHub(ArmResourceManager):
    """IoT Hub Resource

    :example:

    This policy will find all IoT Hubs with 1000 or more dropped messages over the last 72 hours

    .. code-block:: yaml

        policies:
          - name: iothubs-dropping-messages
            resource: azure.iothub
            filters:
              - type: metric
                metric: d2c.telemetry.egress.dropped
                op: ge
                aggregation: total
                threshold: 1000
                timeframe: 72

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Internet Of Things']

        service = 'azure.mgmt.iothub'
        client = 'IotHubClient'
        enum_spec = ('iot_hub_resource', 'list_by_subscription', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.[name, tier, capacity]'
        )
        resource_type = 'Microsoft.Devices/IotHubs'
