.. _azure_examples_sqldatabasewithpremiumsku:

SQL - Find all SQL Databases with Premium SKU
=============================================

Find all SQL databases with Premium SKU.

.. code-block:: yaml

     policies:
       - name: sqldatabase-with-premium-sku
         resource: azure.sqldatabase
         filters:
           - type: value
             key: sku.tier
             op: eq
             value: Premium
