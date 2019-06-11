.. _azure_appinsightslogging:

App Insights Logging & Metrics
==============================

Writing Custodian Logs to Azure App Insights
--------------------------------------------

Custodian can optionally upload its logs in realtime to App Insights,
if a log group is specified.  Each policy’s log output contains policy
name, subscription id and execution id properties.

Usage example using instrumentation key:

    .. code-block:: sh

        custodian run -l azure://<instrumentation_key_guid>

Usage example using resource name:

    .. code-block:: sh

        custodian run -l azure://<resource_group_name>/<app_insights_name>


Writing Custodian Metrics to Azure App Insights
-----------------------------------------------

By default Cloud Custodian generates App Insights metrics on each
policy for the number of resources that matched the set of filters,
the time to retrieve and filter the resources, and the time to execute
actions.

Additionally some filters and actions may generate their own metrics.

You can specify the instrumentation key or resource group and resource
names, similar to Logs output.

In order to enable metrics output, the metrics flag needs to be
specified when running Cloud Custodian:

    .. code-block:: sh

        custodian run --metrics azure://<resource_group_name>/<app_insights_name>
