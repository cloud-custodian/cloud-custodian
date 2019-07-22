Tags - Remove tag From Virtual Machines
=======================================

.. code-block:: yaml

    policies:
        - name: tag-remove
          description: |
            Removes tags from all virtual machines
          resource: azure.vm
          actions:
           - type: untag
             tags: ['TagName', 'TagName2']

