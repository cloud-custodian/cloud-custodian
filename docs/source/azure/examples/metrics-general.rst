Monitor - Filter resources by metrics from Azure Monitor
========================================================

Find VMs with an average Percentage CPU greater than or equal to 75% over the last 12 hours

.. code-block:: yaml

    policies:
      - name: find-busy-vms
        description: Find VMs with avg cpu >= 75% over the last 12 hours
        resource: azure.vm
        filters:
          - type: metric
            metric: Percentage CPU
            aggregation: average
            op: ge
            threshold: 75
            timeframe: 12

Find VMs with a maximum Percentage CPU at or below 10% over the last 24 hours (note the use of
``no_data_action: to_zero`` to treat missing metric values as zeroes)

.. code-block:: yaml

    policies:
      - name: find-underused-vms
        description: Find VMs with maximum cpu <= 10% over the last 24 hours
        resource: azure.vm
        filters:
          - type: metric
            metric: Percentage CPU
            aggregation: maximum
            op: lte
            threshold: 10
            timeframe: 24
            no_data_action: to_zero

Find KeyVaults with more than 1000 API hits in the last hour

.. code-block:: yaml

    policies:
      - name: keyvault-hits
        resource: azure.keyvault
        filters:
        - type: metric
          metric: ServiceApiHit
          aggregation: total
          op: gt
          threshold: 1000
          timeframe: 1

Find SQL servers with less than 10% average DTU consumption over last 24 hours

.. code-block:: yaml

    policies:
      - name: dtu-consumption
        resource: azure.sqlserver
        filters:
          - type: metric
            metric: dtu_consumption_percent
            aggregation: average
            op: lt
            threshold: 10
            timeframe: 24
            filter:  "DatabaseResourceId eq '*'"

The ``dimensions`` key lets a policy filter a resource by a metric of that
resource's parent, restricted back to the resource itself with an OData
filter clause. When ``dimensions`` is set, the filter queries the parent
resource's scope, taken from the ``c7n:parent-id`` annotation, instead of the
resource's own id. Each dimension's ``value`` accepts a literal string, or
one of two sentinels: ``resource-name`` (the resource's own ``name``) or
``resource-id`` (the resource's own ``id``). Because those two strings are
reserved as sentinels, a dimension value can't currently be the literal
string ``resource-name`` or ``resource-id`` themselves.

Find Azure OpenAI model deployments with no requests in the last week, by
querying the parent Cognitive Services account's ``AzureOpenAIRequests``
metric and filtering it back to the deployment via the
``ModelDeploymentName`` dimension

.. code-block:: yaml

    policies:
      - name: unused-openai-deployments
        resource: azure.cognitiveservice-deployment
        filters:
          - type: metric
            metric: AzureOpenAIRequests
            metric_namespace: Microsoft.CognitiveServices/accounts
            aggregation: total
            op: lte
            threshold: 0
            timeframe: 168
            interval: P1D
            no_data_action: to_zero
            dimensions:
              - name: ModelDeploymentName
                value: resource-name

Find storage accounts with low blob count

.. code-block:: yaml

    policies:
      - name: low-blob-count
        resource: azure.storage
        filters:
          - type: storage-metrics
            storage-type: blob
            metric: BlobCount
            aggregation: average
            op: lt
            threshold: 10
            timeframe: 168

Find storage accounts with high queue message count

.. code-block:: yaml

    policies:
      - name: high-queue-messages
        resource: azure.storage
        filters:
          - type: storage-metrics
            storage-type: queue
            metric: QueueMessageCount
            aggregation: average
            op: gt
            threshold: 10000
            timeframe: 24

Find storage accounts with table capacity over threshold

.. code-block:: yaml

    policies:
      - name: high-table-capacity
        resource: azure.storage
        filters:
          - type: storage-metrics
            storage-type: table
            metric: TableCapacity
            aggregation: average
            op: gt
            threshold: 5000000000
            timeframe: 24

Find storage accounts with file share capacity over threshold

.. code-block:: yaml

    policies:
      - name: high-file-capacity
        resource: azure.storage
        filters:
          - type: storage-metrics
            storage-type: file
            metric: FileCapacity
            aggregation: average
            op: gt
            threshold: 10000000000
            timeframe: 24
