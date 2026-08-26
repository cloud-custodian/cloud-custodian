AI Foundry Connections - Audit and manage project connections
==============================================================

Find AI Foundry project connections shared to all users:

.. code-block:: yaml

    policies:
      - name: ai-foundry-connections-shared
        resource: azure.ai-foundry-connection
        filters:
          - type: value
            key: properties.isSharedToAll
            value: true

Set shared connections to private:

.. code-block:: yaml

    policies:
      - name: ai-foundry-connections-make-private
        resource: azure.ai-foundry-connection
        filters:
          - type: value
            key: properties.isSharedToAll
            value: true
        actions:
          - type: update
            properties:
              isSharedToAll: false

Delete connections by category:

.. code-block:: yaml

    policies:
      - name: ai-foundry-connections-delete-legacy
        resource: azure.ai-foundry-connection
        filters:
          - type: value
            key: properties.category
            value: Legacy
        actions:
          - type: delete
