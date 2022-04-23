.. _azure_examples_storage_container_event:

Storage - Monitor newly created Containers for public access
============================================================

Deploy an Azure Function to monitor real-time Blob Storage Container events.
- Filter incoming container events on the ``publicAccess`` property.
- Provides a way to act quickly on any changes to existing containers or creation of new containers.
- Add your own ``actions`` to notify or mitigate as needed.

.. code-block:: yaml

    policies:
      - name: storage_container_public_access_event
        description: 'Identity containers with public access'
        mode:
          type: azure-event-grid
          events:
            - StorageContainerWrite
          provision-options:
            identity:
              type: UserAssigned
              id: custodian_identity
          execution-options:
            output_dir: azure://<storage_account>.blob.core.windows.net/custodian
        resource: azure.storage-container
        filters:
          - type: value
            key: properties.publicAccess
            op: not-equal
            value: None   # Possible values: Blob, Container, None
