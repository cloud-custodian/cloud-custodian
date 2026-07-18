Vertex AI - Manage Endpoints
=============================

Vertex AI Endpoints are used for online prediction serving of machine learning models. Cloud Custodian can help you inventory, filter, and manage these endpoints across multiple locations.

Inventory Endpoints Across Multiple Locations
----------------------------------------------

The following policy queries Vertex AI Endpoints across multiple locations. By default, all Vertex AI-supported regions are queried.

.. code-block:: yaml

    policies:
      - name: vertex-ai-endpoint-inventory
        description: |
          Inventory all Vertex AI Endpoints across all locations
        resource: gcp.vertex-ai-endpoint

Query Specific Locations
-------------------------

You can limit the query to specific locations using the ``query`` parameter:

.. code-block:: yaml

    policies:
      - name: vertex-ai-endpoints-us-only
        description: |
          Query Vertex AI Endpoints only in US regions
        resource: gcp.vertex-ai-endpoint
        query:
          - location: us-central1
          - location: us-east1

Filter Endpoints by Display Name
---------------------------------

Filter endpoints based on their display name using a regular expression:

.. code-block:: yaml

    policies:
      - name: vertex-ai-endpoints-production
        description: |
          Find all production endpoints (display name starts with 'prod-')
        resource: gcp.vertex-ai-endpoint
        filters:
          - type: value
            key: displayName
            op: regex
            value: '^prod-.*'

Filter Endpoints Without Deployed Models
-----------------------------------------

Identify endpoints that have no models deployed (potentially unused):

.. code-block:: yaml

    policies:
      - name: vertex-ai-endpoints-unused
        description: |
          Find endpoints with no deployed models
        resource: gcp.vertex-ai-endpoint
        filters:
          - type: value
            key: deployedModels
            value: []

Filter by Location
------------------

Filter endpoints in a specific location using the ``c7n:location`` annotation:

.. code-block:: yaml

    policies:
      - name: vertex-ai-endpoints-europe
        description: |
          Find all endpoints in Europe regions
        resource: gcp.vertex-ai-endpoint
        filters:
          - type: value
            key: c7n:location.name
            op: regex
            value: '^europe-.*'

Delete Unused Endpoints
------------------------

**Warning**: Deleting an endpoint will automatically undeploy all models from the endpoint. This action cannot be undone.

The following policy deletes endpoints that have no deployed models and haven't been updated in 30 days:

.. code-block:: yaml

    policies:
      - name: vertex-ai-delete-stale-endpoints
        description: |
          Delete endpoints with no deployed models that are older than 30 days
        resource: gcp.vertex-ai-endpoint
        filters:
          - type: value
            key: deployedModels
            value: []
          - type: value
            key: updateTime
            op: less-than
            value_type: age
            value: 30
        actions:
          - type: delete

Delete Endpoints by Name Pattern
---------------------------------

Delete test or development endpoints based on naming convention:

.. code-block:: yaml

    policies:
      - name: vertex-ai-delete-test-endpoints
        description: |
          Delete endpoints with 'test-' or 'dev-' prefix
        resource: gcp.vertex-ai-endpoint
        filters:
          - type: value
            key: displayName
            op: regex
            value: '^(test|dev)-.*'
        actions:
          - type: delete

Notify on Endpoints Without Traffic Split
------------------------------------------

Identify endpoints that may not be configured for safe model rollouts:

.. code-block:: yaml

    policies:
      - name: vertex-ai-endpoints-no-traffic-split
        description: |
          Notify when endpoints have deployed models but no traffic split configured
        resource: gcp.vertex-ai-endpoint
        filters:
          - type: value
            key: deployedModels
            op: not-equal
            value: []
          - or:
            - type: value
              key: trafficSplit
              value: absent
            - type: value
              key: trafficSplit
              value: {}
        actions:
          - type: notify
            to:
              - security-team@example.com
            format: txt
            transport:
              type: pubsub
              topic: projects/my-project/topics/custodian-notifications

Multi-Location Governance
--------------------------

Enforce consistent naming across all locations:

.. code-block:: yaml

    policies:
      - name: vertex-ai-enforce-naming-convention
        description: |
          Find endpoints that don't follow naming convention across all locations
        resource: gcp.vertex-ai-endpoint
        filters:
          - not:
            - type: value
              key: displayName
              op: regex
              value: '^(prod|staging|dev)-[a-z0-9-]+$'

