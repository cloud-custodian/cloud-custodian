.. _azure_examples_sqldatabaseshorttermbackupretention:

Find SQL Databases with a Short Term Backup Retention Less Than 14 Days
=======================================================================

.. code-block:: yaml

     policies:
       - name: short-term-backup-retention
         resource: azure.sqldatabase
         filters:
           - type: short-term-backup-retention
             op: lt
             retention-period-days: 14
