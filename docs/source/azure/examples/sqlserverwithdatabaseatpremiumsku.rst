.. _azure_examples_sqlserverwithdatabaseatpremiumsku:

Find all SQL Servers with a database at the Premium SKU
=======================================================

This policy will find all SQL servers with a database at the Premium SKU. The first filter supplements the
SQL Server model with the SQL Databases that belong to that server. Then, the second filter queries
for any databases that indicate the Premium tier.

.. code-block:: yaml

     policies:
       - name: find-sql-servers-with-premium-database-sku
         resource: azure.sqlserver
         filters:
           - type: sql-database-view
           - type: value
             key: databases[?sku.tier='Premium']
             value: not-null
