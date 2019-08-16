Resource Groups - Remove empty Resource Groups
==============================================

Removes all empty resource groups from the subscription:

.. code-block:: yaml

    policies:
        - name: rg-remove-empty
          description: |
            Removes any empty resource groups from subscription
          resource: azure.resourcegroup
          filters:
            - type: empty-group
          actions:
            - type: delete
