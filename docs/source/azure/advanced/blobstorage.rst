.. _azure_blob_storage_filters:

Azure Blob Storage for value_from Filters
==========================================

Cloud Custodian supports using Azure Blob Storage as a data source for ``value_from`` filters when using the Azure provider (``c7n_azure``). This allows you to store allowlists, denylists, and other reference data in Azure Blob Storage and reference them dynamically in your policies.  All features supported by c7n for other cloud storage providers work with Azure Blob Storage.

URL Format
----------

Azure Blob Storage URLs follow this format:

.. code-block:: text

    azure://storageaccount.blob.core.windows.net/container/path/to/blob.json

The URL structure:

- ``azure://`` - Required URL scheme
- ``storageaccount`` - Your Azure Storage account name
- ``blob.core.windows.net`` - Azure Blob Storage endpoint
- ``container`` - Container name
- ``path/to/blob.json`` - Path to the blob within the container

Authentication
--------------

The Azure Blob Storage resolver automatically uses your Azure credentials from the Cloud Custodian session. No additional authentication configuration is required. The resolver uses the same credentials as your other Cloud Custodian Azure operations.

**Required Permissions:**

Your Azure service principal or managed identity needs the ``Storage Blob Data Reader`` role on the storage account or container to read blobs.

Compression Support
-------------------

Cloud Custodian automatically decompresses files with ``.gz``, ``.gzip``, or ``.zip`` extensions:

.. code-block:: yaml

    policies:
      - name: check-compressed-allowlist
        resource: azure.vm
        filters:
          - type: value
            key: name
            op: in
            value_from:
              url: azure://myaccount.blob.core.windows.net/configs/vms.json.gz
              format: json
              expr: "[].name"

.. note::
   Compression detection is based on file extension, not HTTP headers. Ensure your blob names have the appropriate extension.

Caching
-------

Cloud Custodian automatically caches blob content to improve performance. The cache key includes:

- Blob URL
- Format
- JMESPath expression
- Custom headers (if any)

Cached data is reused across multiple filter evaluations within the same policy run.

Examples
--------

Example 1: Tagging Resources Based on CSV
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

    policies:
      - name: tag-vms-from-csv
        resource: azure.vm
        filters:
          - type: value
            key: name
            op: in
            value_from:
              url: azure://myaccount.blob.core.windows.net/data/vms-to-tag.csv
              format: csv
              expr: 0
        actions:
          - type: tag
            tags:
              managed-by: cloud-custodian
              reviewed: 'true'

Example 2: Multi-Environment Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use string interpolation with ``{account_id}`` and ``{region}``:

.. code-block:: yaml

    policies:
      - name: environment-specific-check
        resource: azure.vm
        filters:
          - type: value
            key: name
            op: in
            value_from:
              url: azure://storage{account_id}.blob.core.windows.net/config-{region}/vms.json
              format: json
              expr: "[].name"

Example 3: Complex Filtering with Multiple Conditions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

    policies:
      - name: complex-vm-check
        resource: azure.vm
        filters:
          - type: value
            key: name
            op: in
            value_from:
              url: azure://myaccount.blob.core.windows.net/configs/vm-rules.json
              format: json
              expr: "rules[?environment=='production' && compliant==`true`].vmName"

**Example blob content (vm-rules.json):**

.. code-block:: json

    {
      "rules": [
        {"vmName": "prod-vm-1", "environment": "production", "compliant": true},
        {"vmName": "prod-vm-2", "environment": "production", "compliant": false},
        {"vmName": "dev-vm-1", "environment": "development", "compliant": true}
      ]
    }

See Also
--------

- :ref:`Azure Getting Started <azure_gettingstarted>`
- `Azure Blob Storage Documentation <https://docs.microsoft.com/en-us/azure/storage/blobs/>`_
