.. _azure_examples_sqldatabasewithpremiumsku:

Find all SQL Databases with Premium SKU
=======================================

This policy will find all SQL databases with Premium SKU.

.. code-block:: yaml

     policies:
       - name: sqldatabase-with-premium-sku
         resource: azure.sqldatabase
         filters:
           - type: value
             key: sku.tier
             op: eq
             value: Premium
