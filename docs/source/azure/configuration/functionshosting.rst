.. _azure_functionshosting:

Azure Functions Hosting
=======================

Overview
########

The Azure provider supports deploying policies into Azure Functions to run them 
inexpensively in your subscription. Currently, you can deploy timer 
triggered functions (azure-periodic) or Event Grid triggered functions 
(azure-event-grid).

The first deployment to an Azure Function will create the following resources 
in your Azure subscription:

- Resource Group: Holds all the resources
- Azure Storage: Serves as the backend data store for the Functions
- Application Insights: Provides logging and metric tracking for the Functions
- App Service Plan: A Linux based consumption plan using the V2 runtime to support Python Functions
- Function App: The Function that executes the given policy

Successive policy deployments will only create a new Function App for the policy, 
because the rest of the infrastructure can be shared.

Note: Ensure you are using at least the minimum `actively supported
<https://devguide.python.org/#status-of-python-branches>`_ version of Python.

Azure Modes
###########

Custodian can run in numerous modes. The default mode is pull.

- pull:
    Default mode, which executes the policy locally to where Custodian is run.

  .. c7n-schema:: mode.pull

- azure-periodic:
    Creates a timer triggered Azure Function to run the policy in Custodian. The timing is executed 
    based on a `user defined cron interval <https://docs.microsoft.com/en-us/azure/azure-functions/functions-bindings-timer#ncrontab-expressions>`_
    , such as every 15 minutes or every hour on weekdays.

  .. c7n-schema:: mode.azure-periodic

- azure-event-grid:
    Creates Event Grid triggered Azure Functions to run the policy in Custodian. This mode allows
    you to apply your policies when events occur. See `Azure Event Grid
    <https://azure.microsoft.com/en-us/services/event-grid/>`_ for more details.

  .. c7n-schema:: mode.azure-event-grid

Provision Options
#################

The following Azure resources are required to support an Azure Function. If they do not 
exist, Custodian will create them as it creates the Azure Function for the policy.

- Storage (shared across functions)
- Application Insights (shared across functions)
- Application Service Plan (shared across functions with optional default auto scale rule)
- Application Service (per function)

Functions can be deployed in either a dedicated Application Service Plan (Basic, Standard or Premium) or in a Consumption plan.
More details on the different hosting models offered by Azure Functions can be found in the `Azure Functions documentation <https://docs.microsoft.com/en-us/azure/azure-functions/functions-scale>`_.
By default, Custodian policies are run using the Consumption hosting model. (i.e. skuTier=dynamic)

Note: Linux Consumption plans are not available in all regions. You will get an error when applying the 
policy if you use an unsupported location. 

You can enable auto scaling for your dedicated App Service Plan. The default auto scaling allows you
to specify the minimum and maximum number of VMs underlying the Functions. The App Service Plan will 
be scaled up if the average RAM usage was more than 80% in the past 10 minutes. 
This option is disabled by default.

The same shared resources from above can be used to service multiple Functions. This is done by
specifying the resources names in the policy deployment definition, or by using the default names every time. 
When deploying a new policy using existing infrastructure, only the new Function will be created.

The default set of parameters for Azure Storage, Application Insights, and Application
Service Plan will deploy the function successfully. To customize the deployment, the defaults 
can be overwritten by setting the ``provision-options`` object on ``mode``. The following keys are 
supported, with their default values shown:

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
provisioned. Application Insights has 20 available locations and thus may not always be in the same
region as the other resources. For details, see `Application Insights availability by region <https://azure.microsoft.com/en-us/global-infrastructure/services/?products=monitor>`_.

If the specified resources already exist in the subscription, discovered by resource group and 
resource name, Custodian will not change the existing resource regardless of the parameters set by the policy.
If a resource does not exist, it will be provisioned using the provided configuration.

You can provide resource IDs to specify existing infrastructure, rather than matching resource group 
and resource name. Please see the third example below for the correct formatting. Custodian verifies 
that the resources defined by the given IDs exist before creating the Function. If the resource 
is missing, Custodian will return an error.

The following example shows how to deploy a policy to a timer-triggered Function that runs every hour. 
The defaults are accepted for Storage and Application Insights, and custom values are provided for the 
Service Plan. This policy deploys a dedicated Basic B1 App Service Plan with the default auto scaling 
turned on. Based on the RAM consumption in the underlying VMs, the App Service Plan will be backed by 1-3 VMs.

.. code-block:: yaml

    policies:
      - name: stopped-vm
        mode:
            type: azure-periodic
            schedule: '0 0 * * * *'
            provision-options:
              servicePlan: 
                name: functionshost
                skuTier: Basic
                skuName: B1
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


The following example shows how to set the name, size and location of all three components
of the supporting infrastructure:

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


The final example shows how to use resource ids to specify existing infrastructure:

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


Authentication Options
######################

Custodian function policies support three different authentications
modes.

 - User Assigned Identities
 - Managed System Identities
 - Service Principal Credentials (embedded)

Its highly recommended to utilize User Assigned Identities, like
Managed System Identities they provide for dynamic automatically
rotated credentials, but they also allow for simplicity of managing
role assignments to a smaller population of IAM resources, instead
of one per policy function.

.. code-block:: yaml

    policies:
      - name: stopped-vm
        mode:
            type: azure-periodic
            schedule: '0 0 * * * *'
            provision-options:
              identity:
                type: UserAssigned
                id: my-custodian-identity
        resource: azure.vm

The identity id can be provided as the user assigned identity's name
or the id, it will be resolved and verified as the policy is
provisioned.

Using a Managed System Identity results in the creation of an identity
per policy function, which then needs subsequent role assignments
before the policy will be able to successfully execute.

.. code-block:: yaml

    policies:
      - name: stopped-vm
        mode:
            type: azure-periodic
            schedule: '0 0 * * * *'
            provision-options:
              identity:
                type: SystemAssigned
        resource: azure.vm


Execution Options
#################

Execution options are not required, but allow you to override defaults that would normally
be provided on the command line in non-serverless scenarios.

Common properties are:

- output_dir
- cache_period
- dryrun
- metrics

The default output directory for an Azure Function is ``/tmp/<random_uuid>``. The following 
example shows how to save the output of the policy to an Azure Storage Account instead of in 
the default Function location.

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

More details on Blob Storage output can be found at :ref:`azure_bloboutput`


Event Grid Functions
####################

Currently, Event Grid Functions are only supported at the subscription level. You can set the function to be 
triggered by write and/or delete events. When an Event Grid Function is deployed, Custodian creates an 
Event Grid Subscription to trigger the new Function when any event occurs in the Subscription. Once triggered,
Custodian only executes the policy if the event was caused by the resource provider and event type specified 
in the policy.

In order to subscribe to an event, you need to provide the resource provider and the action, or provide the string
of one of the `shortcuts <https://github.com/cloud-custodian/cloud-custodian/blob/master/tools/c7n_azure/c7n_azure/azure_events.py>`_. 
For a list of all of the resource providers and their actions, see `Azure Resource Manager resource provider options <https://docs.microsoft.com/en-us/azure/role-based-access-control/resource-provider-operations>`_.

The following example shows an Event Grid Function that runs when a value is written to Key Vault.

.. code-block:: yaml

    policies:
      - name: tag-key-vault-creator
        resource: azure.keyvault
        mode:
          type: azure-event-grid
          events:
            - resourceProvider: Microsoft.KeyVault/vaults
              event: write
        filters:
          - "tag:CreatorEmail": null
        actions:
          - type: auto-tag-user
            tag: CreatorEmail


Management Groups Support
#########################

You can deploy Azure Functions targeting all subscriptions that are part of a specified Management Group.

The following variable allows you to specify Management Group name:

.. code-block:: bash

    AZURE_FUNCTION_MANAGEMENT_GROUP_NAME

It can be used with Function specific Service Principal credentials described in the previous section. 
The Management Group environment variable has the highest priority, so `AZURE_FUNCTION_SUBSCRIPTION_ID` will be ignored.

Timer triggered functions
-------------------------

When the Management Groups option is used with periodic mode, Cloud Custodian deploys a single Azure Function App with multiple Azure Functions following the single-subscription-per-function rule.

Event triggered functions
-------------------------

When the Management Groups option is used with event mode, Cloud Custodian deploys a single Azure Function. It creates an Event Grid subscription for each Subscription in the Management Group delivering events to a single Azure Storage Queue.

Permissions
-----------

The Service Principal used at the Functions runtime is required to have an appropriate level of permissions in each target subscription.

The Service Principal used to provision Azure Functions is required to have an appropriate level of permissions to access Management Groups. If the Service Principal doesn't have `MG Reader` permissions in any child subscription, these subscriptions won't be a part of the Cloud Custodian Azure Function deployment process.
