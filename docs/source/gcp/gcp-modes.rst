.. _gcp-modes:

GCP Modes
===========

Custodian can run in numerous modes depending with the default being pull Mode.

- pull:
    Default mode, which runs locally where custodian is run.

  .. c7n-schema:: PullMode
      :module: c7n.policy

- gcp-periodic:
    Runs in GCP Functions at user defined cron interval.

  .. c7n-schema:: PeriodicMode
      :module: tools.c7n_gcp.c7n_gcp.policy

- gcp-audit:
    Runs in GCP Functions triggered by Audit logs. This allows
    you to apply your policies as soon as events occur. Audit logs creates an event for every
    api call that occurs in your aws account. See `GCP Audit Logs <https://cloud.google.com/logging/docs/audit/>`_
    for more details.

  .. c7n-schema:: ApiAuditMode
      :module: tools.c7n_gcp.c7n_gcp.policy