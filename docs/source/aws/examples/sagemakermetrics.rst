Filtering SageMaker endpoints on CloudWatch metrics
===================================================

The ``metrics`` filter selects SageMaker endpoints by their CloudWatch
metrics: endpoints nobody is calling, GPUs barely being used, instances
that were over-provisioned for the work, and so on.

Overview
--------

Metrics filters select resources according to metric values. A filter
states a condition against those values:

.. code-block:: yaml

    value: 0
    op: lte

A metric has one or more time series, each with zero or more values. The
filter matches a resource when the condition holds for every one of the
values.

The values arrive one per interval: ``days`` sets the window and ``period``
divides it into intervals, in seconds. So ``days: 14, period: 86400`` gives
fourteen daily values, and all fourteen have to satisfy the condition -- one
busy day is enough to exclude a resource. Leave ``period`` out to get a
single value for the whole window.

Missing values for totals
-------------------------

For metrics that count events, or sum values over events, CloudWatch
publishes nothing at all for an interval in which no event occurred. For
many analyses it is better to record non-occurrence as a zero count or sum.
Supply a ``missing-value``, generally 0:

.. code-block:: yaml

    missing-value: 0

Don't do this for utilization metrics. No ``Invocations`` value means no
request arrived, but no ``CPUUtilization`` value means nothing was measured,
which is not the same as nothing being used.

SageMaker metric dimensions
---------------------------

Non-SageMaker resource metrics typically have a single time series.
SageMaker resource metrics typically have multiple time series, reflecting
multiple underlying compute resources. These can be divided in several
ways, so a SageMaker metric typically has several sets of dimensions. See
``c7n/data/sagemaker_metrics.json``.

A filter supplies some dimensions itself. For an endpoint those are
``EndpointName``, and the sub-resources it can enumerate: its production
variants, and the inference components hosted on it. A dimension set is
supported when the filter can supply every dimension in it, or the policy
supplies the rest.

So specifying ``dimensions`` selects a set rather than adding to one.
Naming an instance type for an endpoint selects ``EndpointName,
VariantName, InstanceType`` and queries each variant at that instance
type. Naming dimensions that no published set can be completed from is a
policy error, reported when the policy is loaded rather than as an empty
report later.

SageMaker endpoints
-------------------

An endpoint's series carry two dimensions:

``EndpointName``
   The endpoint's own name, chosen when it was created. The filter supplies
   this for each endpoint it examines.

``VariantName``
   Names a production variant -- a model, an instance type and an instance
   count, serving a share of the endpoint's traffic. An endpoint has at
   least one, and the filter queries every one of them.

To measure a single variant rather than all of them, name it:

.. code-block:: yaml

          - type: metrics
            namespace: /aws/sagemaker/Endpoints
            name: GPUMemoryUtilization
            statistics: Average
            days: 14
            period: 86400
            value: 20
            op: less-than
            dimensions:
              VariantName: primary

A variant that reports no values for a metric is passed over, so an endpoint
with one GPU variant and one CPU variant is judged on the GPU variant alone
for a GPU metric.

Endpoints that serve no traffic
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

An endpoint bills for its instances from creation until it is deleted,
whether or not anything calls it.

.. code-block:: yaml

    policies:
      - name: sagemaker-endpoints-idle
        resource: aws.sagemaker-endpoint
        description: |
          In-service endpoints with no invocations in the last week
        filters:
          - EndpointStatus: InService
          - type: metrics
            name: Invocations
            statistics: Sum
            days: 7
            period: 86400
            value: 0
            op: lte
            missing-value: 0

``missing-value: 0`` is what catches an endpoint that has never been called
at all, for which CloudWatch has no invocation data.

Endpoints with under-used GPUs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Utilization metrics live in their own namespace, so name it:

.. code-block:: yaml

    policies:
      - name: sagemaker-endpoints-underused-gpu
        resource: aws.sagemaker-endpoint
        filters:
          - EndpointStatus: InService
          - type: metrics
            namespace: /aws/sagemaker/Endpoints
            name: GPUMemoryUtilization
            statistics: Average
            days: 14
            period: 86400
            value: 20
            op: less-than

The same namespace carries ``CPUUtilization``, ``MemoryUtilization``,
``GPUUtilization`` and ``DiskUtilization``.

Default namespaces
------------------

.. list-table::
   :header-rows: 1
   :widths: 34 33 33

   * - Resource
     - Default namespace
     - Utilization metrics in
   * - ``sagemaker-endpoint``
     - ``AWS/SageMaker``
     - ``/aws/sagemaker/Endpoints``

For the metric names each namespace offers, see `SageMaker metrics in
CloudWatch
<https://docs.aws.amazon.com/sagemaker/latest/dg/monitoring-cloudwatch.html>`_.
