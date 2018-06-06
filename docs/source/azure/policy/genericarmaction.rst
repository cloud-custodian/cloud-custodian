.. _azure_genericarmaction:

Actions for ARM Resources
=========================

Tags
-------

``AutoTagUser``
  Create a tag listing name of user who created a resource based on scanning
  activity log history.

  .. c7n-schema:: AutoTagUser
      :module: c7n_azure.actions

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

``RemoveTag``
  Remove a set of tags.

  .. c7n-schema:: RemoveTag
      :module: c7n_azure.actions

      .. code-block:: yaml

            policies:
              - name: tag-remove
                description: |
                  Removes tags from all virtual machines
                resource: azure.vm
                actions:
                 - type: untag
                   tags: ['TagName', 'TagName2']
