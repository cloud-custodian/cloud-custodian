.. _azure_functionshosting:

Azure Functions Hosting
=======================

Overview
########

The Azure provider supports deploying policies into Azure Functions to allow
them to run inexpensively in your subscription.

Python support in Azure Functions V2 is in preview and this feature is still immature.

- Linux is currently the only supported operating system.
- Python 3.6+ is the only supported version.
- Only Service Principal authentication is currently supported.

Currently periodic (CRON) and Event Grid functions are supported, however consumption pricing is not
yet supported.

Azure Modes
###########

Custodian can run in numerous modes with the default being pull Mode.

- pull:
    Default mode, which runs locally where custodian is run.

  .. c7n-schema:: mode.pull

- azure-periodic:
    Runs custodian in Azure Functions at a user defined cron interval.

  .. c7n-schema:: mode.azure-periodic

- azure-event-grid:
    Runs custodian in Azure Functions triggered by event-grid events. This allows
    you to apply your policies as soon as events occur. See `Azure Event Grid
    <https://azure.microsoft.com/en-us/services/event-grid/>`_ for more details.

  .. c7n-schema:: mode.azure-event-grid

Provision Options
#################

When deploying an Azure function the following ARM resources are required and created on demand if necessary:

- Storage (shared across functions)
- Application Insights (shared across functions)
- Application Service Plan (shared across functions with optional default auto scale rule)
- Application Service (per function)

Functions can be deployed in either a dedicated Application Service Plan (Basic, Standard or Premium) or in a Consumption plan.
More details on the different hosting models offered by Azure Functions can be found in the `Azure Functions documentation <https://docs.microsoft.com/en-us/azure/azure-functions/functions-scale>`_.
By default, we will run all Custodian policies using the Consumption hosting model. (i.e. skuTier=dynamic)
Linux Consumption is currently only available in the following regions: East Asia, East US, West Europe, and West US

A dedicated plan can service multiple Function Applications.  If you provide the same servicePlanName with all policies or
use the default name then only new Function Applications will be created during deployment, all using the same
shared plan resources.

You can enable default auto scaling option for your dedicated App Service Plan. Default option allows you
to specify minimum and maximum number of underlying VMs. Scaling is performed based on the average RAM usage.
App Service Plan will be scaled up if average RAM usage was more than 80% in the past 10 minutes.
This option is disabled by default.

Execution in Azure functions comes with a default set of configurations for the provisioned
resources. To override these settings you must set 'provision-options' with one of the following
keys:

* servicePlan
    - name (default: cloud-custodian)
    - location (default: East US)
    - resourceGroupName (default: cloud-custodian)
    - skuTier (default: Dynamic) # consumption
    - skuName (default: Y1)
    - autoScale (optional):
         + enabled (default: False)
         + minCapacity (default: 1)
         + maxCapacity (default: 1)
         + defaultCapacity (default: 1)
* storageAccount
    - name (default: custodian + sha256(resourceGroupName+subscription_id)[:8])
    - location (default: servicePlan location)
    - resourceGroupName (default: servicePlan resource group)
* appInsights
    - name (default: servicePlan resource group)
    - location (default: servicePlan location)
    - resourceGroupName (default: servicePlan name)

The location allows you to choose the region to deploy the resource group and resources that will be
provisioned. Application Insights has six available locations and thus can not always be in the same
region as the other resources: West US 2, East US, North Europe, South Central US, Southeast Asia, and
West Europe. The sku, skuCode, and workerSize correlate to scaling up the App Service Plan.

If specified resources already exist in the subscription (discoverable by resource group name and resource name), Cloud Custodian won't make any changes (location, sku)
and will use existing resources as-is. If resource doesn't exist, it will be provisioned using provided configuration.

If you have existing infrastructure, you can specify resource ids for the following items (instead of applying previous schema):

- storageAccount
- servicePlan
- appInsights

If you provide resource ids, Cloud Custodian verifies that resource exists before function app provisioning. It returns an error if resource is missing.

An example on how to set the servicePlanName, accept defaults for the other values and enable default scaling:

This policy deploys dedicated Standard S2 App Service Plan with enabled auto scale rule for 1-3 VMs.
Default scaling rule scales app service plan if total RAM consumption is more than 80%.

.. code-block:: yaml

    policies:
      - name: stopped-vm
        mode:
            type: azure-periodic
            schedule: '0 0 * * * *'
            provision-options:
              servicePlan: 
                name: functionshost
                skuTier: Standard
                skuName: S2
                autoScale:
                  enabled: true
                  minCapacity: 1
                  maxCapacity: 3
                  defaultCapacity: 1
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
- metrics

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
              metrics: azure://<resource_group_name>/<app_insights_name>
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
of one of the `shortcuts <https://github.com/cloud-custodian/cloud-custodian/blob/master/tools/c7n_azure/c7n_azure/azure_events.py>`_.

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

Advanced Authentication Options
###############################

By default the function is both deployed and executed with the credentials and subscription ID you have configured
for the custodian CLI.  You may optionally provide environment variables to use exclusively at function execution time
which also allow you to target your policy towards a subscription ID different than the one to which you are deploying.

The following variables will be obeyed if set:

.. code-block:: bash

    AZURE_FUNCTION_TENANT_ID
    AZURE_FUNCTION_CLIENT_ID
    AZURE_FUNCTION_CLIENT_SECRET
    AZURE_FUNCTION_SUBSCRIPTION_ID

These will be used for function execution, but the normal service principal credentials will still be
used for deployment.

You may provide the service principal but omit the subscription ID if you wish.

Management Groups Support
#########################

You can deploy Azure Functions targeting all subscriptions that are part of specified Management Group.

The following variable allows you to specify Management Group name:

.. code-block:: bash

    AZURE_FUNCTION_MANAGEMENT_GROUP_NAME

It can be used with Function specific Service Principal credentials described before. Management Group environment variable has the highest priority, so `AZURE_FUNCTION_SUBSCRIPTION_ID` will be ignored.

Timer triggered functions
-------------------------

When Management Groups option is used with periodic mode, Cloud Custodian deploys a single Azure Function App with multiple Azure Functions following single subscription per function rule.

Event triggered functions
-------------------------

When Management Groups option is used with event mode, Cloud Custodian deploys single Azure Function. It creates Event Grid subscription for each Subscription in Management Group delivering events to a single Azure Storage Queue.

Permissions
-----------

Service Principal used at the Functions runtime required to have appropriate level of permission in each target subscription.

Service Principal used to provision Azure Functions required to have permissions to access Management Groups. If SP doesn't have `MG Reader` permissions in any child subscription these subscriptions won't be a part of Cloud Custodian Azure Function deployment process.
