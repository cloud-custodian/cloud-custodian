Vertex AI - Publisher Models Inventory and Governance
======================================================

The Vertex AI Model Garden provides access to publisher models (foundation models) from multiple publishers including Google, Anthropic, Meta, Mistral AI, Cohere, and others. These policies help teams inventory available models and govern model choices across all publishers.

Note: This resource uses the v1beta1 API because v1 does not support list operations. The resource automatically queries all known publishers in the Model Garden catalog.

Inventory All Available Publisher Models
-----------------------------------------

List all publisher models available in the Vertex AI Model Garden catalog from all publishers (Google, Anthropic, Meta, Mistral AI, Cohere, etc.).

.. code-block:: yaml

    policies:
      - name: vertex-ai-publisher-models-inventory
        resource: gcp.vertex-ai-publisher-model
        description: |
          Inventory all available publisher models from all publishers in Model Garden

Filter by Launch Stage
-----------------------

Find models that are generally available (GA) versus experimental or preview models.

.. code-block:: yaml

    policies:
      - name: vertex-ai-ga-models
        resource: gcp.vertex-ai-publisher-model
        description: |
          List only GA (Generally Available) publisher models
        filters:
          - type: value
            key: launchStage
            value: GA

      - name: vertex-ai-experimental-models
        resource: gcp.vertex-ai-publisher-model
        description: |
          Report on experimental or preview models
        filters:
          - type: value
            key: launchStage
            op: in
            value: [EXPERIMENTAL, PRIVATE_PREVIEW, PUBLIC_PREVIEW]

Filter by Model Name Pattern
-----------------------------

Find specific publisher models by name pattern (e.g., Gemini, Claude, GPT).

.. code-block:: yaml

    policies:
      - name: vertex-ai-gemini-models
        resource: gcp.vertex-ai-publisher-model
        description: |
          Find all Google Gemini models
        filters:
          - type: value
            key: name
            op: regex
            value: '.*gemini.*'

      - name: vertex-ai-anthropic-models
        resource: gcp.vertex-ai-publisher-model
        description: |
          Find all Anthropic Claude models
        filters:
          - type: value
            key: name
            op: regex
            value: '.*claude.*'

Combine Multiple Filters
-------------------------

Combine filters to find specific model subsets (e.g., GA Gemini models only).

.. code-block:: yaml

    policies:
      - name: vertex-ai-ga-gemini-models
        resource: gcp.vertex-ai-publisher-model
        description: |
          Find only GA Gemini models for production use
        filters:
          - type: value
            key: launchStage
            value: GA
          - type: value
            key: name
            op: regex
            value: '.*gemini.*'

Available Fields
----------------

The following fields are available for filtering:

- ``name``: Full resource name (e.g., ``publishers/google/models/gemini-1.5-flash-002``)
- ``versionId``: Model version identifier
- ``launchStage``: Launch stage (``GA``, ``EXPERIMENTAL``, ``PRIVATE_PREVIEW``, ``PUBLIC_PREVIEW``)
- ``publisherModelTemplate``: Template for deploying the model
- ``openSourceCategory``: License type (e.g., ``PROPRIETARY``)
- ``supportedActions``: Links to notebooks, AI Studio, evaluation pipelines

