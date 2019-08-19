.. _azure_examples_teams_new_resource_group:

Resource Group - Generate a Teams Message on Create
===================================================

This policy will send a notification to a Microsoft Teams channel when
a new resource group is created in the subscription. There is a few minute 
delay between the resource group being created and the notification appearing.

In order to target the correct Teams channel, you will need to insert the 
custom incoming webhook for the channel. If you do not have a webhook set up,
please see `Setting up a custom incoming webhook <https://docs.microsoft.com/en-us/microsoftteams/platform/concepts/connectors/connectors-using#setting-up-a-custom-incoming-webhook>`_.

We are using an `actionable message card <https://docs.microsoft.com/en-us/outlook/actionable-messages/send-via-connectors>`_ 
to provide a link to the new resource group. Note: linking to portal pages within 
Azure is not supported by all web browsers.

To run the policy, you must replace ``<your_webhook_here>`` with the correct url.

For more information on how the event grid function works please see :ref:`azure_functionshosting`

.. code-block:: yaml

    policies:
      - name: notify-new-resource-group
        description: |
          Generates a Teams notification when a new resource group is created
        resource: azure.resourcegroup
        mode:
          type: azure-event-grid
          events: [{
            resourceProvider: Microsoft.Resources/subscriptions/resourceGroups,
            event: write
          }]
        actions:
          - type: webhook
            url: <your_webhook_here>
            batch: false
            body: >
              {
                "@context": `https://schema.org/extensions`,
                "@type": `MessageCard`,
                "themeColor": `0072C6`,
                "title": `New Resource Group Created`,
                "text": join('', [`A new resource group has been created in subscription `, account_id, `.\n\nResource Group Name: `, resource.name, `\n\nResource Group Location: `, resource.location])
                "potentialAction": [
                  {
                    "@type": `OpenUri`,
                    "name": `Open In Portal`,
                    "targets": [
                    {
                      "os": `default`,
                      "uri": join('',[`https://ms.portal.azure.com/#@microsoft.onmicrosoft.com/resource`, resource.id, `/overview`])
                    }
                    ]
                  }
                ]
              }