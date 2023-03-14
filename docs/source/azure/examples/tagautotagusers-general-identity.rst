.. _azure_examples_autotagusers:

Tags - Automatically tag the creator of a resource or resource group
====================================================================

General notes:

- It is strongly recommended to always use ``resource-type`` filter when using ``armresource``.
- Tag operation is allowed only for ARM resources supported by Cloud Custodian, error message is logged
  for all unknown and unsupported resources.
- In non-event mode (periodic function or local execution), the action will look in Azure 
  Activity Logs up to 90 days prior to execution to find the user email (default). It will attempt 
  to identify the first user or Service Principal that performed the 'write' operation for each resource.
- In event mode, the action will use the data from the event to determine the user or principal
  that performed the action. The **days** option is not applicable in this mode.
- **Note**: Resource Groups aren't a part of ``armresource`` type, so tags needs to be added separately.
- **Note**: Service Principals do not have email addresses and their tag values will be the application id.

Tag all resource groups with the email address of the creator. The email address is
taken from the oldest user to 'write' the resource group within the last 10 days.

.. code-block:: yaml

      policies:
        - name: azure-auto-tag-creator-resource-groups
          resource: azure.resourcegroup
          description: |
            Tag all existing resource groups with the 'CreatorEmail' tag; looking up to 10 days prior.
          actions:
           - type: auto-tag-user
             tag: CreatorEmail
             days: 10

Tag all virtual networks, storage accounts and virtual machines with their creator
email, limited to 10 days of logs to identify the creator.

.. code-block:: yaml

      policies:
        - name: azure-auto-tag-creator-resources
          resource: azure.armresource
          description: |
            Tag all arm resources of the VMs, VNETs and Storage accounts with the
            'Creator Email' tag; looking up to 10 days prior.
          filters:
            - type: resource-type
              values:
                - Microsoft.Network/virtualNetworks
                - Microsoft.Storage/storageAccounts
                - Microsoft.Compute/virtualMachines
          actions:
           - type: auto-tag-user
             tag: CreatorEmail
             days: 10

Event grid triggered policy to tag all virtual machines and storage accounts
with the creator email. The creator email is contained in the event message, 
so days is not needed.

.. code-block:: yaml

      policies:
        - name: azure-auto-tag-creator
          mode:
            type: azure-event-grid
            events: ['VmWrite', 'StorageWrite']
          resource: azure.armresource
          description: |
            Tag all new VMs and StorageAccounts with the 'Creator Email' tag.
            Note: 'resource-type' filter is not required because policy is not triggered by other resources.
          actions:
           - type: auto-tag-user
             tag: CreatorEmail


