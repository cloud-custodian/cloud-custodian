.. _azure_examples_sqldatabaselongtermbackupretention:

Find SQL Databases with a Monthly Long Term Backup Retention More Than 1 Year
=============================================================================

.. code-block:: yaml

     policies:
       - name: long-term-backup-retention
         resource: azure.sqldatabase
         filters:
           - type: long-term-backup-retention-policy
             backup-type: monthly
             op: gt
             retention-period: 1
             retention-period-units: year
