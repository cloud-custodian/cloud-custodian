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

Whether a metric behaves this way is up to the service publishing it, and
endpoints don't: an endpoint reports a zero for an interval nothing called
it, so a policy looking for idle endpoints needs no missing value. See
`Endpoints that serve no traffic`_ for when one is called for.

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

A metric's identity is the whole set, so only the sets CloudWatch
publishes can be asked for.  The AWS documentation lists the dimensions a
metric can be filtered by rather than the sets it is published under, and
some of those combinations carry no data.

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

Which dimensions you can supply depends on the kind:

``VariantName``
   For a classic endpoint.  A component endpoint reports its invocations
   against components rather than variants, so naming a variant leaves it
   with nothing to measure.

``InferenceComponentName``
   For a component endpoint.  Naming one deselects every classic endpoint,
   so unless a ``missing-value`` is supplied the filter selects none of
   them.


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

An endpoint reports a zero for an interval in which nothing called it,
whichever way it hosts its models, so its own values answer the question
and no ``missing-value`` is needed here.

Supply one when a metric may have no values at all: for an endpoint
created part way through the window, or for a metric its kind of endpoint
doesn't publish.  Then ``missing-value: 0`` reads the absence as a zero,
and leaving it out passes the endpoint over.

Endpoints with under-used GPUs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Utilization metrics are reported per variant, like invocations:

.. code-block:: yaml

    policies:
      - name: sagemaker-endpoints-underused-gpu
        resource: aws.sagemaker-endpoint
        filters:
          - EndpointStatus: InService
          - type: metrics
            name: GPUMemoryUtilization
            statistics: Average
            days: 14
            period: 86400
            value: 20
            op: less-than

``CPUUtilization``, ``MemoryUtilization``, ``GPUUtilization`` and
``DiskUtilization`` are reported the same way.

Each metric belongs to one CloudWatch namespace, which the filter looks
up from the metric name, so policies don't name it. For the metrics
SageMaker publishes, see `SageMaker metrics in CloudWatch
<https://docs.aws.amazon.com/sagemaker/latest/dg/monitoring-cloudwatch.html>`_.
