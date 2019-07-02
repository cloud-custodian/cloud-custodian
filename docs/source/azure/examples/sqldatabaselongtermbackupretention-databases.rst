.. _azure_examples_sqldatabaselongtermbackupretention:

SQL - Find SQL Databases with a monthly long term backup retention more than one year
===================================================================================

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
