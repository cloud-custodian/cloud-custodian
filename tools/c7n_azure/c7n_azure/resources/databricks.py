# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager

from c7n.exceptions import PolicyExecutionError
from c7n.utils import type_schema


@resources.register('databricks')
class Databricks(ArmResourceManager):
    """Databricks Resource

    :example:

    Returns all databricks named my-test-databricks

    .. code-block:: yaml

        policies:
          - name: get-databricks
            resource: azure.databricks
            filters:
              - type: value
                key: name
                op: eq
                value: my-test-databricks

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']

        service = 'azure.mgmt.databricks'
        client = 'DatabricksClient'
        enum_spec = ('workspaces', 'list_by_subscription', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name'
        )
        resource_type = 'Microsoft.Databricks/workspaces'


@Databricks.action_registry.register('set-cmk-encryption')
class DatabricksSetCmkEncryptionAction(AzureBaseAction):
    """Encrypt a workspace's DBFS root storage with a customer-managed key.

    The workspace must already be prepared for encryption
    (``prepareEncryption``), and its storage account identity must have
    get, wrap key and unwrap key access to the key. Workspaces that are
    not prepared are skipped with a warning. ``key-version`` is optional.

    :example:

    .. code-block:: yaml

        policies:
          - name: databricks-dbfs-cmk-encryption
            resource: azure.databricks
            filters:
              - properties.parameters.prepareEncryption.value: true
              - type: value
                key: properties.parameters.encryption.value.keySource
                op: ne
                value: Microsoft.Keyvault
            actions:
              - type: set-cmk-encryption
                key-vault-uri: https://example-vault.vault.azure.net/
                key-name: example-key
    """

    schema = type_schema(
        'set-cmk-encryption',
        required=['key-vault-uri', 'key-name'],
        **{
            'key-vault-uri': {'type': 'string'},
            'key-name': {'type': 'string'},
            'key-version': {'type': 'string'},
        },
    )
    permissions = ('Microsoft.Databricks/workspaces/write',)
    api_version = '2024-05-01'

    def process(self, resources, event=None):
        # Checked here, not in validate(): policies are validated before
        # variables are expanded, and an unset variable stays literal text.
        uri = self.data['key-vault-uri']
        if not uri.startswith('https://'):
            raise PolicyExecutionError(
                "set-cmk-encryption: key-vault-uri must start with https://, got %r" % uri)

        resources = self.filter_resources(
            resources, 'properties.parameters.prepareEncryption.value', (True,))
        return super().process(resources, event)

    def _process_resources(self, resources, event):
        # The base class logs and swallows errors outside pytest, so a failed key
        # change would leave the run looking successful. Set the rest, then raise.
        self._prepare_processing()
        failures = []
        for resource in resources:
            try:
                self._log_modified_resource(resource, self._process_resource(resource))
            except Exception as e:
                self.log.error(
                    "Setting customer-managed key on '%s' in resource group '%s' failed: %s",
                    resource.get('name'), resource.get('resourceGroup'), e,
                    exc_info=True, extra=self._get_action_log_metadata(resource))
                failures.append(e)
        if failures:
            raise failures[0]

    def _prepare_processing(self):
        self.client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')

    def _process_resource(self, resource):
        # The workspaces PATCH API only updates tags, so read the whole workspace
        # and PUT it back. Not the databricks SDK: its 2018-04-01 models would drop
        # newer settings such as publicNetworkAccess from the body.
        workspace = self.client.resources.get_by_id(
            resource_id=resource['id'], api_version=self.api_version
        )
        self.set_key(workspace.properties)
        self.client.resources.begin_create_or_update_by_id(
            resource_id=resource['id'], api_version=self.api_version, parameters=workspace
        ).result()
        return "Set customer-managed key '{}'".format(self.data['key-name'])

    def set_key(self, properties):
        """Set the key as the DBFS root encryption in workspace ``properties``."""
        encryption = {
            'keySource': 'Microsoft.Keyvault',
            'keyvaulturi': self.data['key-vault-uri'],
            'KeyName': self.data['key-name'],
        }
        if 'key-version' in self.data:
            encryption['keyversion'] = self.data['key-version']
        properties['parameters']['encryption'] = {'value': encryption}
