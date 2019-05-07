.. _modes:

Modes
=====

Custodian can run in numerous modes depending on the provider with the default being pull Mode.

- pull:
    Default mode, which runs locally where custodian is run.

  .. c7n-schema:: PullMode
      :module: c7n.policy

- periodic:
    Runs in AWS lambda at user defined cron interval.

  .. c7n-schema:: PeriodicMode
      :module: c7n.policy

- azure-periodic:
    Runs in Azure Functions at user defined cron interval.

  .. c7n-schema:: AzurePeriodicMode
      :module: tools.c7n_azure.c7n_azure.policy

- gcp-periodic:
    Runs in GCP Functions at user defined cron interval.

  .. c7n-schema:: PeriodicMode
      :module: tools.c7n_gcp.c7n_gcp.policy

- phd:
    Runs in AWS lambda and is triggered by Personal Health Dashboard events.

  .. c7n-schema:: PHDMode
      :module: c7n.policy

- cloudtrail:
    Runs in AWS lambda and is triggered by cloudtrail events.

  .. c7n-schema:: CloudTrailMode
      :module: c7n.policy

- ec2-instance-state:
    Runs in AWS lambda and is triggered by ec2 instance state changes

  .. c7n-schema:: EC2InstanceState
      :module: c7n.policy

- asg-instance-state:
    Runs in AWS lambda and is triggered by asg instance state changes

  .. c7n-schema:: ASGInstanceState
      :module: c7n.policy

- guard-duty:
    Runs in AWS lambda and is triggered by guard-duty responses.

  .. c7n-schema:: GuardDutyMode
      :module: c7n.policy

- config-rule:
    Runs in AWS lambda and runs as a config service rule.

  .. c7n-schema:: ConfigRuleMode
      :module: c7n.policy

- azure-event-grid:
    Runs in Azure Functions triggered by event-grid events.

  .. c7n-schema:: AzureEventGridMode
      :module: tools.c7n_azure.c7n_azure.policy

- gcp-audit:
    Runs in GCP Functions triggered by audit events.

  .. c7n-schema:: ApiAuditMode
      :module: tools.c7n_gcp.c7n_gcp.policy