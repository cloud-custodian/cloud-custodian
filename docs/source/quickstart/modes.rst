.. _modes:

Modes
=====

Custodian can run in numerous modes depending on the provider with the default being pull Mode.

- pull:
    Default mode, which runs locally where custodian is run.

- periodic:
    Runs in AWS lambda at user defined cron interval.

- azure-periodic:
    Runs in Azure Functions at user defined cron interval.

- gcp-periodic:
    Runs in GCP Functions at user defined cron interval.

- phd:
    Runs in AWS lambda and is triggered by Personal Health Dashboard events.

- cloudtrail:
    Runs in AWS lambda and is triggered by cloudtrail events.

- ec2-instance-state:
    Runs in AWS lambda and is triggered by ec2 instance state changes

- asg-instance-state:
    Runs in AWS lambda and is triggered by asg instance state changes

- guard-duty:
    Runs in AWS lambda and is triggered by guard-duty responses.

- config-rule:
    Runs in AWS lambda and runs as a config service rule.

- azure-event-grid:
    Runs in Azure Functions triggered by event-grid events.

- gcp-audit:
    Runs in GCP Functions triggered by audit events.