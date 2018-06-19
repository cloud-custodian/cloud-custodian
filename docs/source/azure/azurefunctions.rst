.. azurefunctions:

Azure Functions Support
-----------------------

Cloud Custodian Integration
===========================
Support of Azure Functions in Cloud Custodian is still in progress.


Provision Options
#################

When running in Azure functions, a storage account, application insights instance, and an app service
plan is provisioned in your subscription to enable running the functions in an app service.

Execution in Azure functions comes with a default set of configurations for the provisioned
resources. To override these setting you must set 'provision-options' with one of the following
keys:

- location (default: West US 2)
- appInsightsLocation (default: West US 2)
- sku (default: Standard)
- skuCode (default: S1)
- workerSize (default: 0)

The location allows you to choose the region to deploy the resource group and resources that will be
provisioned. Application Insights has six available locations and thus can not always be in the same
region as the other resources: West US 2, East US, North Europe, South Central US, Southeast Asia, and
West Europe. The sku, skuCode, and workerSize correlate to scaling up the App Service Plan.

An example on how to set the provision-options when running in azure-functions mode:

.. code-block:: yaml

    policies:
      - name: stopped-vm
        mode:
            type: azure-functions
            provision-options:
              location: East US
              appInsightsLocation: East US
         resource: azure.vm
         filters:
          - type: instance-view
            key: statuses[].code
            op: not-in
            value_type: swap
            value: "PowerState/running"



