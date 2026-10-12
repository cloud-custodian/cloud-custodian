.. _azure_setup_notify_prereqs:

Advanced Azure Setup: Auto-Tagging & Notifications
==================================================

Moving beyond local CLI execution, production Cloud Custodian deployments in Azure run as serverless Azure Functions triggered by event streams (Event Grid and Activity Logs). This guide covers setting up auto-tagging of resource creators and configuring event-driven notifications using both Azure Logic Apps and c7n-mailer.

.. contents::
   :local:
   :depth: 2

Overview of Execution Modes
---------------------------

While local execution (``custodian run``) is ideal for ad-hoc audits, real-time compliance requires event-driven execution modes:

* **azure-stream**: Deploys Cloud Custodian as an Azure Function app triggered by Azure Event Grid events (such as resource creation or modification).
* **azure-periodic**: Deploys Cloud Custodian as a scheduled Azure Function app running on a timer (e.g. every hour or daily).

Auto-Tagging Resource Creators
-----------------------------

A primary requirement for cloud governance is tracking who created a given resource. When deployed in ``azure-stream`` mode, Cloud Custodian captures Azure Activity Log events and extracts creator identity to tag resources dynamically.

Prerequisites
~~~~~~~~~~~~~
* An active Azure Subscription.
* Azure CLI authenticated with permissions to create Function Apps and Event Grid subscriptions.
* Azure Storage Account for Function App runtime state.

Auto-Tagging Policy Example
~~~~~~~~~~~~~~~~~~~~~~~~~~

Save the following configuration as ``auto_tag_creator.yml``:

.. code-block:: yaml

    policies:
      - name: azure-auto-tag-creator
        description: |
          Automatically tag newly created resource groups and VMs with creator identity.
        resource: azure.vm
        mode:
          type: azure-stream
          events:
            - write
          provision-options:
            servicePlan:
              name: custodian-functions-plan
              sku: Y1 # Consumption Plan
        filters:
          - "tag:CreatorEmail": absent
        actions:
          - type: auto-tag-user
            tag: CreatorEmail

Deploying the Policy
~~~~~~~~~~~~~~~~~~~~

Run the deployment command:

.. code-block:: bash

    custodian run --output-dir=. auto_tag_creator.yml

Upon execution, Cloud Custodian provisions an Azure Function App that listens to Azure Event Grid write events. When a new Virtual Machine is provisioned, the function executes within seconds and appends the ``CreatorEmail`` tag containing the UPN or Email of the creator.

Event-Driven Notifications
--------------------------

When non-compliant resources are detected or tagged, security and operations teams must be notified immediately. Cloud Custodian supports two notification architectures in Azure:

1. **Azure Logic Apps** (Direct HTTP Webhooks - Quickest setup)
2. **c7n-mailer with Azure Service Bus** (Enterprise queue-based routing)

Notification Architecture Comparison
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

+------------------------+-------------------------------------+-------------------------------------+
| Feature                | Azure Logic App Webhook             | c7n-mailer (Azure Service Bus)      |
+========================+=====================================+=====================================+
| Setup Complexity       | Low (No daemon required)            | Medium (Requires mailer deployment) |
+------------------------+-------------------------------------+-------------------------------------+
| Transport              | HTTP POST / Webhook endpoint        | Azure Service Bus Queue             |
+------------------------+-------------------------------------+-------------------------------------+
| Delivery Channels      | MS Teams, Slack, Email, ServiceNow  | Email (SMTP/SendGrid), Slack, Webhooks |
+------------------------+-------------------------------------+-------------------------------------+
| Scalability            | Native Azure Logic App scaling      | Distributed queue worker            |
+------------------------+-------------------------------------+-------------------------------------+

Option 1: Notifications via Azure Logic Apps
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Azure Logic Apps provide a low-code HTTP trigger endpoint that can format and route notifications to Microsoft Teams, Slack, or Email.

1. **Create the Logic App**:
   * Navigate to Azure Portal -> Logic Apps -> Create Logic App.
   * Add a trigger: **When an HTTP request is received**.
   * Copy the generated HTTP POST URL.

2. **Configure Custodian Policy**:

Use the ``webhook`` action in your policy to POST event payloads to the Logic App endpoint:

.. code-block:: yaml

    policies:
      - name: azure-vm-unencrypted-notify
        resource: azure.vm
        mode:
          type: azure-stream
          events:
            - write
        filters:
          - type: storage-profile
            key: osDisk.managedDisk.storageAccountType
            op: not-equal
            value: Premium_LRS
        actions:
          - type: webhook
            url: "https://prod-00.eastus.logic.azure.com:443/workflows/YOUR_LOGIC_APP_TRIGGER_URL"
            method: POST
            batch: true

Option 2: Notifications via c7n-mailer and Azure Service Bus
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For centralized notification templating, email delivery, and multi-channel routing, use ``c7n-mailer``.

1. **Provision Azure Service Bus**:
   * Create an Azure Service Bus Namespace (Standard or Premium tier).
   * Create a Queue named ``custodian-notifications``.
   * Retrieve the primary connection string.

2. **Configure Mailer Daemon (`mailer.yml`)**:

.. code-block:: yaml

    queue_url: "endpoint=sb://your-namespace.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=YOUR_KEY;EntityPath=custodian-notifications"
    from_address: custodian@yourdomain.com
    smtp_server: smtp.office365.com
    smtp_port: 587
    smtp_username: custodian@yourdomain.com
    smtp_password: YOUR_SMTP_PASSWORD

3. **Configure Custodian Policy to Push to Queue**:

.. code-block:: yaml

    policies:
      - name: azure-notify-noncompliant-vm
        resource: azure.vm
        mode:
          type: azure-stream
          events:
            - write
        filters:
          - "tag:Environment": absent
        actions:
          - type: notify
            slack_template: default
            to:
              - user@yourdomain.com
            transport:
              type: asb
              queue: https://your-namespace.servicebus.windows.net/custodian-notifications

Verification & Diagnostics
--------------------------

To verify your serverless auto-tagging and notification setup:

1. **Inspect Function App Logs**:
   Stream logs using Azure CLI:

   .. code-block:: bash

       az webapp log tail --name custodian-auto-tag-creator --resource-group custodian-functions-rg

2. **Test Event Grid Delivery**:
   Check Event Grid Subscription metrics in the Azure Portal to confirm events are delivering to the Function App trigger.

3. **Validate Mailer Worker**:
   Run ``c7n-mailer`` locally or in a container to verify message consumption:

   .. code-block:: bash

       c7n-mailer -c mailer.yml --run
