.. _azure_examples_app_service_cors:

App Services - Filter By CORS Configuration
===============================================================

Filter to select all Application Services (Web Apps and Functions) with a
Cross-Origin Resource Sharing (CORS) configuration set to allow all origins.

.. code-block:: yaml

    policies:
      - name: app-service-cors-policy
        description: |
          Get all wildcard CORS configurations
        resource: azure.webapp
        filters:
          - type: configuration
            key: cors.allowedOrigins
            value: '*'
            op: contains