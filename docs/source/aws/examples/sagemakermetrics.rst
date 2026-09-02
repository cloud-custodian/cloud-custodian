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

Filtering which metric data for a resource is considered
--------------------------------------------------------

Sometimes, you may not want to use all of the metric data for a
resource metric filter. To some degree, you can choose which metric
data to use.

AWS CloudWatch defines `Dimensions
<https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_Dimension.html>`_,
which are used to identify metric time series.  Each resource metric
defines one or more dimension sets. A dimension set defines the keys
that can be used to look up individual metric time series.

For example, SageMaker endpoints define a dimension set consisting of
Endpoint name and variant name.  You can look up an individual metric
by supplying a specific endpoint name and a specific variant name.

Most resource-metrics have only one dimension set, but SageMaker
resources typically have many.

To limit the metric data used, specify one or more dimension values::

  dimensions:
    VariantName: gpu

For SageMaker endpoints, supplying a variant of ``gpu`` means only
the metrics identified for the GPU variant are used.

Allowable dimensions are documented for each resource below.  They
exclude resource identifiers (e.g. "EndpointName") , which aren't
allowed in `dimensions` options.

SageMaker Endpoints
-------------------

There are two kinds of endpoints:

- Classic endpoints that deploy models in variants

- Inference-component endpoints that deploy models in inference
  components in variants

Allowable dimensions are any combination of:

- VariantName
- InstanceType
- InferenceComponentName

Specifying InferenceComponentName deselects metrics for all classic
endpoints.  This means that unless a ``missing-value`` is used, the
filter won't select any classic endpoints.


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
