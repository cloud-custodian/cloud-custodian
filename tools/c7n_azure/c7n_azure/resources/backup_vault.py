from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('backup-vault')
class BackupVault(ArmResourceManager):
    """Azure Backup Vault

    :example:

    This policy will find all Data Protection Backup Vaults

    .. code-block:: yaml

        policies:
          - name: backup-vaults
            resource: azure.backup-vault

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Security']

        service = 'azure.mgmt.dataprotection'
        client = 'DataProtectionMgmtClient'
        enum_spec = ('backup_vaults', 'get_in_subscription', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.provisioningState',
        )
        resource_type = 'Microsoft.DataProtection/backupVaults'
