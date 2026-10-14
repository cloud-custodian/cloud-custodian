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
real-time endpoints don't: one reports a zero for an interval nothing
called it, so a policy looking for idle real-time endpoints needs no
missing value. An asynchronous endpoint can have no
``InvocationsProcessed`` at all: one that hasn't processed a request has none.
See `Endpoints that serve no traffic`_.

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

Allowable dimensions are documented for each resource below.  A
resource's own identifier (e.g. "EndpointName") is supplied for you, so
there's rarely a reason to name it; naming a different resource's leaves
nothing to measure.

SageMaker Endpoints
-------------------

There are three kinds of endpoints:

- Classic endpoints that deploy models in variants

- Inference-component endpoints that deploy models in inference
  components in variants

- Asynchronous endpoints, whose configuration has an
  ``AsyncInferenceConfig``

Which dimensions you can supply depends on the metric, and for
invocations on the kind of endpoint as well.

Utilization metrics -- ``CPUUtilization`` and the rest -- are reported per
variant whichever kind of endpoint publishes them, so ``VariantName``
narrows them in every case:

.. code-block:: yaml

    dimensions:
      VariantName: gpu

Invocations and latencies are reported per variant by a classic endpoint
and per component by a component endpoint, so those two kinds take different
dimensions:

``VariantName``
   Narrows a classic endpoint's invocations to one variant.  A component
   endpoint doesn't report invocations per variant, so naming one leaves it
   with nothing to measure, and unless a ``missing-value`` is supplied it
   drops out of the results.

``InferenceComponentName``
   Narrows a component endpoint's invocations to one component.  Naming one
   leaves every classic or asynchronous endpoint with nothing to measure,
   and the same applies to them.

Either way, an endpoint with nothing to measure is decided by the
``missing-value``, if the policy gives one, exactly as an endpoint whose
series reported nothing would be.

Asynchronous endpoints
~~~~~~~~~~~~~~~~~~~~~~

Of the real-time invocation metrics, an asynchronous endpoint publishes
only ``Invocation4XXErrors``, ``Invocation5XXErrors`` and ``ModelLatency``;
it counts requests in ``InvocationsProcessed`` instead. `Asynchronous
inference metrics
<https://docs.aws.amazon.com/sagemaker/latest/dg/async-inference-monitor.html>`_
lists the rest, and misspells it ``InvocationsProcesssed``.

The queue belongs to the endpoint rather than a variant, so
``ApproximateBacklogSize``, ``ApproximateBacklogSizePerInstance``,
``ApproximateAgeOfOldestRequest`` and ``HasBacklogWithoutCapacity`` take no
``VariantName``. The rest are reported per variant.


Endpoints that serve no traffic
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

An endpoint bills for the instances it holds, whether or not anything
calls it.

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

A real-time endpoint reports a zero for an interval in which nothing called
it, whichever way it hosts its models, so its own values answer the
question and no ``missing-value`` is needed here.

Supply one when a metric may have no values at all: for an endpoint
created part way through the window, or for a metric its kind of endpoint
doesn't publish.  Then ``missing-value: 0`` reads the absence as a zero,
and leaving it out passes the endpoint over. For ``Invocations``, that means
a missing value matches every asynchronous endpoint, busy or not.

The policy above passes over asynchronous endpoints, which publish no
``Invocations``. Their ``InvocationsProcessed`` needs ``missing-value: 0``,
and because real-time endpoints have no ``InvocationsProcessed`` either,
that branch also requires an ``AsyncInferenceConfig``:

.. code-block:: yaml

    policies:
      - name: sagemaker-endpoints-idle-including-async
        resource: aws.sagemaker-endpoint
        description: |
          In-service endpoints, real-time or async, that processed no
          requests in the last week
        filters:
          - EndpointStatus: InService
          - or:
            - type: metrics
              name: Invocations
              statistics: Sum
              days: 7
              period: 86400
              value: 0
              op: lte
            - and:
              - AsyncInferenceConfig: present
              - type: metrics
                name: InvocationsProcessed
                statistics: Sum
                days: 7
                period: 86400
                value: 0
                op: lte
                missing-value: 0

An async endpoint whose requests are still queued, such as one scaled to
zero instances, has processed none either; ``ApproximateBacklogSize`` shows
whether any are waiting.

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
