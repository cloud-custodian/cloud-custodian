.. _azure_azurefunctions:

Azure Functions Support
-----------------------

Overview
===========================
The Azure provider supports deploying policies into Azure Functions to allow
them to run inexpensively in your subscription.

Python support in Azure Functions V2 is in preview and this feature is still immature.

- Linux is currently the only supported operating system.
- Python 3.6 is the only supported version.
- Only Service Principal authentication is currently supported.

Currently periodic (CRON) and Event Grid functions are supported, however consumption pricing is not
yet supported.

Provision Options
#################

When deploying an Azure function the following ARM resources are required and created on demand if necessary:

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

- servicePlan
  - name (default: cloud-custodian)
  - location (default: West US 2)
  - resourceGroupName (default: cloud-custodian)
  - skuTier (default: Basic)
  - skuName (default: B1)
- storageAccount
  - name (default: custodianstorageaccount)
  - location (default: servicePlan location)
  - resourceGroupName (default: servicePlan resource group)
- appInsights
  - name (default: servicePlan resource group)
  - location (default: servicePlan location)
  - resourceGroupName (default: servicePlan name)

The location allows you to choose the region to deploy the resource group and resources that will be
provisioned. Application Insights has six available locations and thus can not always be in the same
region as the other resources: West US 2, East US, North Europe, South Central US, Southeast Asia, and
West Europe. The sku, skuCode, and workerSize correlate to scaling up the App Service Plan.

If specified resources already exist in the subscription (discoverable by resource group name and resource name), Cloud Custodian won't make any changes (location, sku)
and will use existing resources as-is. If resource doesn't exist, it will be provisioned using provided configuration.

If you have existing infrastructure, you can specify resource ids for the following itesm (instead of applying previous schema):

- storageAccount
- servicePlan
- appInsights

If you provide resource ids, Cloud Custodian verifies that resource exists before function app provisioning. It returns an error if resource is missing.

An example on how to set the servicePlanName and accept defaults for the other values:

.. code-block:: yaml

    policies:
      - name: stopped-vm
        mode:
            type: azure-periodic
            schedule: '0 0 * * * *'
            provision-options:
              servicePlan: 
                name: functionshost
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
              servicePlan:
                name: functionshost
                location: East US
                skuTier: Standard
                skuName: S1
              appInsights:
                location: East US
              storageAccount:
                name: sampleaccount
                location: East US
         resource: azure.vm
         filters:
          - type: instance-view
            key: statuses[].code
            op: not-in
            value_type: swap
            value: "PowerState/running"


An example on how to use existing infrastructure:

.. code-block:: yaml

    policies:
      - name: stopped-vm
        mode:
            type: azure-periodic
            schedule: '0 0 * * * *'
            provision-options:
              servicePlan: /subscriptions/<subscription_id>/resourceGroups/cloud-custodian/providers/Microsoft.Web/serverFarms/existingResource
              appInsights: /subscriptions/<subscription_id>/resourceGroups/cloud-custodian/providers/microsoft.insights/components/existingResource
              storageAccount: /subscriptions/<subscription_id>/resourceGroups/cloud-custodian/providers/Microsoft.Storage/storageAccounts/existingResource
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
              servicePlan:
                name: functionshost
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
