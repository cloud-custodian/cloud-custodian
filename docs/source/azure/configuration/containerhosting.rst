.. _azure_containerhosting:

Azure Container Hosting
=======================

The Azure provider can be run in a containerized environment using the official cloud custodian 
`docker image <https://hub.docker.com/r/cloudcustodian/c7n>`_. The Azure Container Host knows 
how to handle both periodic and event based policies.

The Azure Container Host will read policies from an Azure Blob Container and, depending on their mode,
will listen for event triggers or run them periodically. Event triggers are pulled from an event 
queue within a storage account.

To run the container, pass the docker command as `/usr/local/bin/python3 -m c7n_azure.container_host.host`
and authenticate through environment variables (see :ref:`azure_authentication`). It is also important
to make sure that the container host is authenticated as a contributor on the policy storage and a 
message processor on the event queue.

There are 3 important environment variables that are specific to the container host. 

* `AZURE_EVENT_QUEUE_RESOURCE_ID`: The resource ID for a storage account for the event queue.
* `AZURE_EVENT_QUEUE_NAME`: The name of the event queue. If this queue does not exist, it will be created.
* `AZURE_CONTAINER_STORAGE`: The URI to an azure blob container that will hold all of the policies for this container host.

Supported Policy Modes
######################

The container host will only run policies with one of the following modes specified. Otherwise, 
the policy will be ignored.

- container-periodic

    Run the policy periodically based on a provided crontab schedule.

  .. c7n-schema:: mode.container-periodic

- container-event

    Run the policy when particular events are dropped into the specified event queue.

  .. c7n-schema:: mode.container-event

Deployment Options
##################

Azure Container Instance
------------------------

The ARM template to deploy the Azure Container Host is provided for deploying an ACI instance
against a single subscription using a `user assigned identity <https://docs.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/overview>`_ 
for authentication.

Here is an example deployment of the ARM template using the azure cli:

.. code-block:: bash

    az group deployment create \
        --resource-group my-resource-group \
        --template-file tools/ops/azure/container-host/aci/aci-template.json \
        --parameters \
            aci_name=cloud-custodian \
            user_assigned_identity_name=my-uai \
            azure_subscription_id=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
            azure_event_queue_name=custodian-aci-queue \
            azure_container_storage=https://myStorageAccount.blob.core.windows.net/aci-policies \
            azure_event_queue_resource_id=/subscriptions/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/resourceGroups/my-resource-group/providers/Microsoft.Storage/storageAccounts/myStorageAccount

Kubernetes (Helm Chart)
-----------------------

A helm chart is provided that will deploy a set of cloud custodian containers against a set of 
subscriptions to be monitored. For information on how to customize the values, reference 
the helm chart's values.yaml.

.. code-block:: yaml

    # sample-values.yaml

    defaultEnvironment:
      AZURE_TENANT_ID: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      AZURE_CLIENT_ID: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      AZURE_EVENT_QUEUE_NAME: "cloud-custodian-events"
    
    defaultSecretEnvironment:
      AZURE_CLIENT_SECRET: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

    subscriptionHosts:
      - name: "my-first-subscription"
        environment:
          AZURE_SUBSCRIPTION_ID: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
          AZURE_CONTAINER_STORAGE: "https://firstStorageAccount.blob.core.windows.net/cloud-custodian-policies"
          AZURE_EVENT_QUEUE_RESOURCE_ID: "/subscriptions/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/resourceGroups/myResourceGroup/providers/Microsoft.Storage/storageAccounts/firstStorageAccount"
      - name: "my-second-subscription"
        environment:
          AZURE_SUBSCRIPTION_ID: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
          AZURE_CONTAINER_STORAGE: "https://secondStorageAccount.blob.core.windows.net/more-policies"
          AZURE_EVENT_QUEUE_RESOURCE_ID: "/subscriptions/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/resourceGroups/myOtherResourceGroup/providers/Microsoft.Storage/storageAccounts/secondStorageAccount"

To deploy the chart:

.. code-block:: bash

    helm upgrade --install --debug --namespace cloud-custodian --values /path/to/sample-values.yaml my-cloud-custodian-deployment tools/ops/azure/container-host/chart


Helm Chart Deployment Script
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Additionally, a utility script for deploying the helm chart against either a single subscription 
or all subscriptions in a management group is provided. When deploying for a management group,
all of the containers will share the same policy storage and storage account for event queues.

.. code-block:: bash

    # Usage
    $ python tools/ops/azure/container-host/chart/deploy_chart.py --help

    Usage: deploy_chart.py [OPTIONS] COMMAND [ARGS]...

    Options:
    -d, --deployment-name TEXT
    -s, --deployment-namespace TEXT
    --image-repository TEXT
    --image-tag TEXT
    --image-pull-policy TEXT
    --dry-run / --no-dry-run
    --help                          Show this message and exit.

    Commands:
    management_group
    subscription



    # subscription subcommand
    $ python tools/ops/azure/container-host/chart/deploy_chart.py subscription --help

    Usage: deploy_chart.py subscription [OPTIONS]

    Options:
    -n, --name TEXT           [required]
    -e, --env <TEXT TEXT>...
    --secret-env <TEXT TEXT>...
    --help                    Show this message and exit.



    # management_group subcommand
    $ python tools/ops/azure/container-host/chart/deploy_chart.py management_group --help

    Usage: deploy_chart.py management_group [OPTIONS]

    Options:
    -m, --management-group-id TEXT  [required]
    -e, --env <TEXT TEXT>...
    --secret-env <TEXT TEXT>...
    --help                          Show this message and exit.

Examples
________

Deploy against a single subscription:

.. code-block:: bash

    python tools/ops/azure/container-host/chart/deploy_chart.py \
        --deployment-name azure-c7n \
        --deployment-namespace cloud-custodian \
        subscription \
        --name my-subscription \
        --env AZURE_TENANT_ID "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
        --env AZURE_SUBSCRIPTION_ID "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
        --secret-env AZURE_CLIENT_ID "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
        --env AZURE_CLIENT_SECRET "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
        --env AZURE_CONTAINER_STORAGE "https://myStorageAccount.blob.core.windows.net/policyContainer" \
        --env AZURE_EVENT_QUEUE_RESOURCE_ID "/subscriptions/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/resourceGroups/myResourceGroup/providers/Microsoft.Storage/storageAccounts/myStorageAccount" \
        --env AZURE_EVENT_QUEUE_NAME "my-subscription-c7n"

Deploy against a management group:

.. code-block:: bash

    python tools/ops/azure/container-host/chart/deploy_chart.py \
        --deployment-name azure-c7n \
        --deployment-namespace cloud-custodian \
        management_group \
        --management-group-id "my-management-group" \
        --env AZURE_TENANT_ID "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
        --env AZURE_CLIENT_ID "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
        --secret-env AZURE_CLIENT_SECRET "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
        --env AZURE_CONTAINER_STORAGE "https://myStorageAccount.blob.core.windows.net/policyContainer" \
        --env AZURE_EVENT_QUEUE_RESOURCE_ID "/subscriptions/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/resourceGroups/myResourceGroup/providers/Microsoft.Storage/storageAccounts/myStorageAccount" \

