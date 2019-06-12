.. _azure_examples_sqldatabaseupdateretentionpolicies:

Update SQL Database Retention Policies
======================================

Update any SQL Database short term retentions to at least 7 days

.. code-block:: yaml

     policies:
        - name: update-short-term-backup-retention-policy
          resource: azure.sqldatabase
          filters:
          - type: short-term-backup-retention-policy
             op: lt
             retention-period-days: 7
          actions:
          - type: update-short-term-backup-retention-policy
             retention-period-days: 7

Enforce a 1 month maximum retention for weekly backups on all SQL Databases

.. code-block:: yaml

     policies:
        - name: update-long-term-backup-retention-policy
          resource: azure.sqldatabase
          filters:
          - type: long-term-backup-retention-policy
             backup-type: weekly
             op: gt
             retention-period: 1
             retention-period-units: months
          actions:
          - type: update-long-term-backup-retention-policy
             backup-type: weekly
             retention-period: 1
             retention-period-units: months
