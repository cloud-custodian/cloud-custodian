Resize an Application Service Plan
==============================================================
Count or Size can be provided individually or together.

.. code-block:: yaml

  policies:
    - name: azure-resize-plan
      resource: azure.appserviceplan
      actions:
       - type: resize-plan
         size: F1 # F1, D1, S1, S2, S3, P1, P2, P3
         count: 1
