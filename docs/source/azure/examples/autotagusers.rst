Automatically tag the creator of a resource or resource group.
==============================================================

- In non-event mode, the action will look up Azure Activity Logs up to 90 days prior to execution (default). It will attempt to identify the first user or service principal that performed the 'write' operation for each resource.
- In event mode, the action will use the data from the event to determine the user or principal that performed the action. The **days** option is not applicable in this mode.
- **Note**: Service Principals do not have email addresses and their tag values will be the application id.

.. code-block:: yaml

      policies:
        - name: azure-auto-tag-creator
          resource: azure.resourcegroup
          description: |
            Tag all existing resource groups with the 'CreatorEmail' tag; looking up to 10 days prior.
          actions:
           - type: auto-tag-user
             tag: CreatorEmail
             days: 10

.. code-block:: yaml

      policies:
        - name: azure-auto-tag-creator
          mode:
            type: azure-event-grid
            events: [{
                resourceProvider: 'Microsoft.Compute/virtualMachines',
                event: 'write'
            }]
          resource: azure.vm
          description: |
            Tag all existing virtual machines with the 'CreatorEmail' tag using ARM events.
          actions:
           - type: auto-tag-user
             tag: CreatorEmail


