.. _azure-modes:

Azure Modes
===========

Custodian can run in numerous modes depending with the default being pull Mode.

- pull:
    Default mode, which runs locally where custodian is run.

  .. c7n-schema:: PullMode
      :module: c7n.policy

- azure-periodic:
    Runs custodian in Azure Functions at a user defined cron interval.

  .. c7n-schema:: AzurePeriodicMode
      :module: tools.c7n_azure.c7n_azure.policy


- azure-event-grid:
    Runs custodian in Azure Functions triggered by event-grid events. This allows
    you to apply your policies as soon as events occur. See `Azure Event Grid
    <https://azure.microsoft.com/en-us/services/event-grid/>`_ for more details.

  .. c7n-schema:: AzureEventGridMode
      :module: tools.c7n_azure.c7n_azure.policy