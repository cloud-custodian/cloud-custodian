.. _azure_genericarmaction:

Generic Actions
================

Tags
-----

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

``TagTrim``
      Automatically remove tags from an azure resource.

      Azure Resources and Resource Groups have a limit of 15 tags.
      In order to make additional tag space on a set of resources,
      this action can be used to remove enough tags to make the
      desired amount of space while preserving a given set of tags.
      Setting the space value to 0 removes all tags but those
      listed to preserve.

      .. code-block:: yaml

          - policies:
             - name: azure-tag-trim
               comment: |
                 Any instances with 14 or more tags get tags removed until
                 they match the target tag count, in this case 13, so
                 that we free up tag slots for another usage.
               resource: azure.resourcegroup
               filters:
                   # Filter down to resources that do not have the space
                   # to add additional required tags. For example, if an
                   # additional 2 tags need to be added to a resource, with
                   # 15 tags as the limit, then filter down to resources that
                   # have 14 or more tags since they will need to have tags
                   # removed for the 2 extra. This also ensures that metrics
                   # reporting is correct for the policy.
                   type: value
                   key: "[length(Tags)][0]"
                   op: ge
                   value: 14
               actions:
                 - type: tag-trim
                   space: 2
                   preserve:
                    - OwnerContact
                    - Environment
                    - downtime
                    - custodian_status

      .. c7n-schema:: TagTrim
            :module: c7n_azure.actions
