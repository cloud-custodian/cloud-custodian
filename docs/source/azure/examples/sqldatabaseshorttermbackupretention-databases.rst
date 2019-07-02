.. _azure_examples_sqldatabaseshorttermbackupretention:

SQL - Find SQL Databases with a short term backup retention less than 14 days
=============================================================================

.. code-block:: yaml

     policies:
       - name: short-term-backup-retention
         resource: azure.sqldatabase
         filters:
           - type: short-term-backup-retention
             op: lt
             retention-period-days: 14
