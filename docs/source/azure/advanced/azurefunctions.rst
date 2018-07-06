.. _azure_azurefunctions:

Azure Functions Support
-----------------------

Overview
===========================
The Azure provider supports deploying policies into Azure Functions to allow
them to run inexpensively in your subscription.

Python support in Azure Functions V2 is in preview and this feature is still immature.

Currently periodic (CRON) functions are supported and consumption pricing is not yet supported.


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



