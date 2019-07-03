.. _azure_azurepolicy:

Azure Policy Comparison
=======================

Cloud Custodian and Azure Policy have significant overlap in scenarios they can accomplish with
regard to compliance implementations. These areas of overlap can make it unclear to new users
which tool is appropriate for a specific task.

Both tools apply rules to resources, and have some ability to take actions, but they do it
in very different ways which are complimentary rather than redundant.

*Azure Policy* is reliable and efficient for building a custom validation layer on deployments
to prevent deviation from customer defined rules. There is minimal extensibility possible and it
is not a general purpose Azure rules engine.

*Cloud Custodian* can not prevent deployments, but rather runs periodically or based on events
in the subscription. It has many purpose-built Filters and Actions that help with
common scenarios like configuring Firewalls, identifying expensive resources, and
notifying users about violations.  Rules can do anything the Azure SDK can do, and you can
implement custom ones in Python if you need to.

When reviewing your requirements, we recommend first identifying the requirements that can
be implemented via Azure Policy.  Custodian can then be used to implement the remaining 
requirements.  Custodian is also frequently used to add a second layer of protection or 
mitigation actions to requirements covered by Azure Policy.

In the event that you prefer to manage everything through Cloud Custodian for consistency in a
multi-cloud environment you can take advantage of the Custodian support for managing Azure Policy
with Custodian filters and actions.  This way your Custodian rules can actually ensure Azure Policy
is configured correctly.


Examples
--------

In Azure Policy we can require users to include an owner tag on every Virtual Machine.
If they create any deployment without one the Portal or API will return an error code.

The users will manually update their ARM templates or use the Tag UI in the Azure Portal
during resource creation.

Here is what that Azure Policy might look like:

.. code-block:: json

    {
       "properties": {
          "displayName": "Enforce tag and its value on resource groups",
          "description": "Enforces a required tag and its value on resource groups.",
          "mode": "All",
          "parameters": {
             "tagName": {
                "type": "String",
                "metadata": {
                   "description": "Name of the tag, such as costCenter"
                }
             }
          },
          "policyRule": {
             "if": {
                "allOf": [
                   {
                      "field": "type",
                      "equals": "Microsoft.Compute/virtualMachine"
                   },
                   {
                      "not": {
                         "field": "[concat('tags[',parameters('tagName'), ']')]",
                         "exists": "true"
                      }
                   }
                ]
             },
             "then": {
                "effect": "deny"
             }
          }
       }
    }


In Custodian we can deploy a Custodian Policy which is triggered by Virtual Machine creation
events and automatically finds the identity of the creator and writes the tag without any
required user action.

.. code-block:: yaml

    policies:
      - name: azure-auto-tag-creator
        mode:
          type: azure-event-grid
          events: ['VmWrite']
        resource: azure.vm
        description: Tag all new VMs with the 'Creator Email' tag.
        actions:
         - type: auto-tag-user
           tag: CreatorEmail


A simple example of a non-compliance related rule might be cleaning up orphaned resources.
This is out-of-scope for Azure Policy because it is not a deployment property filter.

With Cloud Custodian a policy to find and delete unused Network Interfaces would look
like this:

.. code-block:: yaml

    policies:
      - name: orphaned-nic
        resource: azure.networkinterface
        filters:
          - type: value
            key: properties.virtualMachine
            value: null
        actions:
          - type: delete
