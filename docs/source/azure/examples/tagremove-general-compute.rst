Tags - Remove tag From Virtual Machines
=======================================

Remove the tags `TagName` and `TagName2` from all VMs in the subscription

.. code-block:: yaml

    policies:
        - name: tag-remove
          description: |
            Removes tags from all virtual machines
          resource: azure.vm
          actions:
           - type: untag
             tags: ['TagName', 'TagName2']

