Tags - Add tag to Virtual Machines
==================================

Add the tag `TagName` with value `TagValue` to all VMs in the subscription

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

