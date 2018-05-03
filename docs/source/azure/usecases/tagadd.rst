Add Tag To Virtual Machines
==============================

.. code-block:: yaml

    policies:
        - name: tag-add
          description: |
            Adds a tag to all virtual machines
          resource: azure.vm
          actions:
           - type: tag
             tag: TagName
             value: TagValue

