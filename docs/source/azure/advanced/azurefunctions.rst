.. _azure_azurefunctions:

Azure Functions Support
-----------------------

Overview
===========================
The Azure provider supports deploying policies into Azure Functions to allow
them to run inexpensively in your subscription.

Python support in Azure Functions V2 is in preview and this feature is still immature.

Currently periodic (CRON) and Event Grid functions are supported, but consumption pricing is not
yet supported.


Provision Options
#################

When deploying an Azure function the following ARM resources are required and created on demand:

- Storage (shared across functions)
- Application Insights (shared across functions)
- Application Service Plan (shared across functions)
- Application Service (per function)

A single Application Service Plan (Basic, Standard or Premium) can service a large number
of Application Service Instances.  If you provide the same servicePlanName with all policies or
use the default name then only new Applications will be created during deployment, all using the same
shared plan resources.

Execution in Azure functions comes with a default set of configurations for the provisioned
resources. To override these settings you must set 'provision-options' with one of the following
keys:

- location (default: West US 2)
- appInsightsLocation (default: West US 2)
- servicePlanName (default: cloud-custodian)
- sku (default: Basic)
- skuCode (default: B1)
- workerSize (default: 0)

The location allows you to choose the region to deploy the resource group and resources that will be
provisioned. Application Insights has six available locations and thus can not always be in the same
region as the other resources: West US 2, East US, North Europe, South Central US, Southeast Asia, and
West Europe. The sku, skuCode, and workerSize correlate to scaling up the App Service Plan.

An example on how to set the servicePlanName and accept defaults for the other values:

.. code-block:: yaml

    policies:
      - name: stopped-vm
        mode:
            type: azure-periodic
            schedule: '0 0 * * * *'
            provision-options:
              servicePlanName: functionshost
         resource: azure.vm
         filters:
          - type: instance-view
            key: statuses[].code
            op: not-in
            value_type: swap
            value: "PowerState/running"


An example on how to set size and location as well:

.. code-block:: yaml

    policies:
      - name: stopped-vm
        mode:
            type: azure-periodic
            schedule: '0 0 * * * *'
            provision-options:
              servicePlanName: functionshost
              location: East US
              appInsightsLocation: East US
              sku: Standard
              skuCode: S1
         resource: azure.vm
         filters:
          - type: instance-view
            key: statuses[].code
            op: not-in
            value_type: swap
            value: "PowerState/running"


Execution Options
#################

Execution options are not required, but allow you to override defaults that would normally
be provided on the command line in non-serverless scenarios.

Common properties are:

- output_dir
- cache_period
- dryrun

Output directory defaults to `/tmp/<random_uuid>` but you can point it to a Azure Blob Storage container instead

.. code-block:: yaml

    policies:
      - name: stopped-vm
        mode:
            type: azure-periodic
            schedule: '0 0 * * * *'
            provision-options:
              servicePlanName: functionshost
            execution-options:
              output_dir: azure://yourstorageaccount.blob.core.windows.net/custodian
         resource: azure.vm
         filters:
          - type: instance-view
            key: statuses[].code
            op: not-in
            value_type: swap
            value: "PowerState/running"

More details on Blob Storage output are at :ref:`azure_bloboutput`


Event Grid Functions
####################

Currently, support for event grid functions is at the subscription level and can listen to write and delete
events. When deploying an event grid function, an Event Grid Subscription is created that triggers the Azure Function
when any event is triggered in the subscription. Cloud custodian filters to the events you passed to your policy and
ignores all other events.

In order to subscribe on an event you need to provide the resource provider and the action, or provide the string
of one of the `shortcuts <https://github.com/capitalone/cloud-custodian/blob/master/tools/c7n_azure/c7n_azure/azure_events.py>`_.

.. code-block:: yaml

    policies:
        - name: tag-key-vault-creator
          resource: azure.keyvault
          mode:
            type: azure-event-grid
            events: [{
                resourceProvider: 'Microsoft.KeyVault/vaults',
                event: 'write'
              }]
          filters:
            - "tag:CreatorEmail": null
          actions:
            - type: auto-tag-user
              tag: CreatorEmail
              days: 10
