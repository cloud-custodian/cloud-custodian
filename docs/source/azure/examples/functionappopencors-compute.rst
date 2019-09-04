.. _azure_examples_function_app_cors:

Function Apps - Find Functions with Open CORS policy
===============================================================

Filter to select all Function Apps with open an CORS policy. An open CORS policy 
here defined as a wildcard, "*".

.. code-block:: yaml

    policies:
      - name: function-cors-policy
        description: |
          Get all functions open to all ips
        resource: azure.webapp
        filters:
          - type: configuration
            key: cors.allowedOrigins
            value: '*'
            op: contains