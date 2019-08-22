.. _azure_examples_resize_app_service_plan:

App Service - Resize All Application Service Plans
==================================================

Count or Size can be provided individually or together. Add filters to 
resize specific Application Service Plans.

Note: This will not resize consumption based plans.

.. code-block:: yaml

  policies:
    - name: azure-resize-plan
      resource: azure.appserviceplan
      actions:
       - type: resize-plan
         size: F1 # F1, B1, B2, B3, S1, S2, S3, P1v2, P2v2, P3v2
         count: 1
