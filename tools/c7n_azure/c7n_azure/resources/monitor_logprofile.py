# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.utils import ResourceIdParser

from c7n.filters.core import ValueFilter
from c7n.utils import local_session, type_schema


@resources.register('monitor-log-profile')
class MonitorLogprofile(ArmResourceManager):
    """Azure Monitor Log Profile Resource

    :example:

    Returns Monitor Log Profile resources

    .. code-block:: yaml

         policies:
          - name: basic-monitor-log-profile
            resource: azure.monitor-log-profile
            filters:
              - type: value
                key: categories
                op: in
                value: ["Delete"]

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Monitoring']

        service = 'azure.mgmt.monitor'
        client = 'MonitorManagementClient'
        enum_spec = ('log_profiles', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Insights/logprofiles'


@MonitorLogprofile.filter_registry.register('monitor-storage')
class MonitorLogStorageFilter(ValueFilter):
    """Check monitor log profile storage

    :example:

    .. code-block:: yaml

        policies:
          - name: test-monitor-storage
            resource: azure.monitor-log-profile
            filters:
                - type: monitor-storage
                  key: properties.encryption.keySource
                  op: eq
                  value_type: normalize
                  value: microsoft.keyvault
    """
    schema = type_schema('monitor-storage', rinherit=ValueFilter.schema)
    schema_alias = False

    def process(self, resources, event=None):
        self.session = local_session(self.manager.session_factory)
        self.storageClient = self.session.client("azure.mgmt.storage.StorageManagementClient")
        matched = []
        for profile in resources:
            storage_name = ResourceIdParser.get_resource_name(
                profile['properties']['storageAccountId'])
            storage_group = ResourceIdParser.get_resource_group(
                profile['properties']['storageAccountId'])
            storage_properties = self.storageClient.storage_accounts.get_properties(
                storage_group, storage_name)
            if self.match(storage_properties.serialize(True)):
                matched.append(profile)
        return matched
