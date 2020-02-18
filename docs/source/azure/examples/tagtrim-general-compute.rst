Tags - Trim tags From Virtual Machines
======================================

Azure Resources and Resource Groups have a limit of 15 tags. This action can be used 
to remove enough tags to make the desired amount of space while preserving 
a given set of tags. Setting space to 0 will remove all tags not listed to preserve.

This example limits the number of tags on all virtual machines to 12, while
making sure to keep `TagName1` and `TagName2` preserved.

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