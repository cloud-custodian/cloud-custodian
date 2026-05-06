AI Foundry Projects - Find projects by name and location
=========================================================

Find Azure AI Foundry projects in ``eastus``:

.. code-block:: yaml

    policies:
      - name: ai-foundry-projects-eastus
        resource: azure.ai-foundry-project
        filters:
          - type: value
            key: location
            value: eastus

Find AI Foundry projects with names starting with ``prod-``:

.. code-block:: yaml

    policies:
      - name: ai-foundry-projects-prod
        resource: azure.ai-foundry-project
        filters:
          - type: value
            key: name
            op: regex
            value: '^prod-.*'
