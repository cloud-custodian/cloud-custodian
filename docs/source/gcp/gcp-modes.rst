.. _gcp-modes:

GCP Modes
===========

Custodian can run in numerous modes depending with the default being pull mode.

- pull:
    Default mode, which runs locally where custodian is run.

  .. c7n-schema:: mode.pull

- gcp-periodic:
    Runs in GCP Functions triggered by Cloud Scheduler at user defined cron interval. Default region the function is
    deployed to is ``us-central1``. In case you want to change that, use the cli ``--region`` flag.

  .. c7n-schema:: mode.gcp-periodic

- gcp-audit:
    Runs in GCP Functions triggered by Audit logs. This allows
    you to apply your policies as soon as events occur. Audit logs creates an event for every
    api call that occurs in your gcp account. See `GCP Audit Logs <https://cloud.google.com/logging/docs/audit/>`_
    for more details. Default region the function is deployed to is ``us-central1``. In case you want to change that,
    use the cli ``--region`` flag.

  .. c7n-schema:: mode.gcp-audit

