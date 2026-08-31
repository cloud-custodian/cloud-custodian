Filtering SageMaker based on CloudWatch metrics
===============================================

SageMaker publishes no metric for an endpoint or a job as a whole. Every
series it publishes is dimensioned one level finer -- per production variant
for an endpoint, per instance for a job -- so the ``metrics`` filter queries
one series per variant, or per instance, and combines them.

One resource, several series
----------------------------

CloudWatch identifies a metric by its namespace, its name, and its exact set
of dimensions; each distinct set is a separate series. An endpoint named
``inference`` with variants ``blue`` and ``green`` has two series for
``Invocations``:

.. code-block:: text

    AWS/SageMaker  Invocations  {EndpointName: inference, VariantName: blue}
    AWS/SageMaker  Invocations  {EndpointName: inference, VariantName: green}

There is no ``{EndpointName: inference}`` series to ask for, and CloudWatch
returns statistics only for dimension sets that were actually published --
never a total across them.

The filter therefore reads the endpoint's variants and queries each one. The
endpoint matches only if **every datapoint of every series** satisfies the
condition, so this policy means "no variant of this endpoint has been
invoked on any of the last 7 days":

.. code-block:: yaml

    policies:
      - name: sagemaker-endpoints-idle
        resource: aws.sagemaker-endpoint
        description: |
          Endpoints billing for instances while serving no traffic
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

``days`` sets the window and ``period`` divides it into buckets, so
``days: 7, period: 86400`` asks for seven daily sums -- and all seven, from
both variants, have to be zero. Widen ``period`` to cover the whole window
and you are instead testing a single aggregate over the week.

An endpoint whose variants have different instance types will have variants
that publish nothing for a given metric: GPU metrics do not exist for a
variant with no GPU. Such a series returns no datapoints and drops out of
the comparison, leaving the endpoint judged on the variants that do report.
Scope the policy rather than relying on that.

Batch transform, training and processing jobs work the same way, one series
per instance:

.. code-block:: yaml

    policies:
      - name: sagemaker-training-jobs-idle-gpu
        resource: aws.sagemaker-job
        filters:
          - type: metrics
            name: GPUUtilization
            statistics: Average
            days: 1
            period: 3600
            value: 10
            op: less-than

missing-value belongs with totals
---------------------------------

When a series has no data at all, the filter has nothing to compare and
skips the resource -- it can never match. ``missing-value`` supplies a
stand-in datapoint so the comparison happens anyway. Buckets *within* a
series that have no data are simply absent from the results; nothing can be
substituted for an individual day.

Whether a stand-in is legitimate depends on what the metric counts:

- For a total, use it. No ``Invocations`` datapoint means no invocation
  occurred, so ``missing-value: 0`` states a fact -- and it is what lets the
  policy above find an endpoint that has never been called since it was
  created, which is the most idle endpoint of all.

- For a utilization average, leave it out. No ``CPUUtilization`` datapoint
  means nothing was measured, not that nothing was used. Filling in ``0``
  asserts an instance was idle when all you know is that it did not report.

Naming dimensions explicitly
----------------------------

The filter fills in the dimensions itself, which is what makes the policies
above short. To query a different set, give ``dimensions`` and the filter
uses yours instead of expanding over variants or instances:

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
              VariantName: gpu

The dimension sets SageMaker publishes, and what the filter uses by default:

.. list-table::
   :header-rows: 1
   :widths: 22 30 48

   * - Resource
     - Default namespace
     - Dimensions
   * - ``sagemaker-endpoint``
     - ``AWS/SageMaker``
     - ``EndpointName`` + ``VariantName``, one query per production variant.
       Also published: ``EndpointName, VariantName, InstanceType`` for
       variants using instance pools, and ``InstanceId`` /
       ``AcceleratorId`` when the endpoint config enables enhanced metrics.
   * - ``sagemaker-job``
     - ``/aws/sagemaker/TrainingJobs``
     - ``Host``, one query per instance
   * - ``sagemaker-processing-job``
     - ``/aws/sagemaker/ProcessingJobs``
     - ``Host``, one query per instance
   * - ``sagemaker-transform-job``
     - ``/aws/sagemaker/TransformJobs``
     - ``Host``, one query per instance

Endpoint *utilization* metrics -- ``CPUUtilization``, ``MemoryUtilization``,
``GPUUtilization``, ``GPUMemoryUtilization``, ``DiskUtilization`` -- are in
the ``/aws/sagemaker/Endpoints`` namespace rather than the default, so those
policies have to name it. Invocation metrics are in the default.

A job's ``Host`` value is ``<job-name>/algo-<n>`` for training and
processing jobs, and ``<job-name>/<instance-id>`` for transform jobs, whose
instance ids no SageMaker API reports. The filter discovers the values from
CloudWatch, which only lists metrics that reported within the last two
weeks.

References
----------

- `SageMaker metrics in CloudWatch
  <https://docs.aws.amazon.com/sagemaker/latest/dg/monitoring-cloudwatch.html>`_
- `GetMetricStatistics
  <https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricStatistics.html>`_
