.. azurefunctions:

Azure Functions Support
-----------------------

Cloud Custodian Integration
===========================
Support of Azure Functions in Cloud Custodian is still in development.


Provision Options
#################

When running in Azure functions, a storage account, Application Insights instance, and an App Service
is provisioned in your subscription per policy to enable running the functions in an App Service.

An App Service Plan is also required to run, but Plans can have multiple App Services to one App Service
Plan so it is recommended that you only provision one and continue to use the same App Service plan by
providing the same servicePlanName with all policies or use the default name.

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

An example on how to set the provision-options when running in azure functions mode:

.. code-block:: yaml

    policies:
      - name: stopped-vm
        mode:
            type: azure-periodic
            provision-options:
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



