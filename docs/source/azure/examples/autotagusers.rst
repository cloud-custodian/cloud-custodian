Automatically tag the creator of a resource or resource group.
==============================================================

- This action will look up Activity Logs up to 90 days (default), in an attempt to identify the first user to perform the 'write' operation for the resources or resource groups. 

.. code-block:: yaml

      policies:
        - name: azure-auto-tag-creator
          resource: azure.resourcegroup
          description: |
            Tag all existing resource groups with the 'CreatorEmail' tag
          actions:
           - type: auto-tag-user
             tag: CreatorEmail             
             days: 10

