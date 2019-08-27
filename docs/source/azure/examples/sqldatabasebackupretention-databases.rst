.. _azure_examples_sqldatabasebackupretention:

SQL - Find databases with specific retention options
====================================================

Find SQL Databases with a short term backup retention less than 14 days.

.. code-block:: yaml

     policies:
       - name: short-term-backup-retention
         resource: azure.sqldatabase
         filters:
           - type: short-term-backup-retention
             op: lt
             retention-period-days: 14

Find SQL Databases with a monthly long term backup retention period more than one year

.. code-block:: yaml

     policies:
       - name: long-term-backup-retention
         resource: azure.sqldatabase
         filters:
           - type: long-term-backup-retention
             backup-type: monthly
             op: gt
             retention-period: 1
             retention-period-units: year
