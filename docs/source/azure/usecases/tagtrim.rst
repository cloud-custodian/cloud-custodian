Trim Tags From Virtual Machines
================================
-   Azure Resources and Resource Groups have a limit of 15 tags, in order to make additional tags space on a set of resources, this action can be used to remove enough tags to make the desired amount of space while preserving a given set of tags.

.. code-block:: yaml

    policies:
        - name: tag-trim
          description: |
            Trims tags from resources to make additional space
          resource: azure.vm
          actions:
           - type: tag-trim
             preserve: ['TagName1', 'TagName2']
             space: 3