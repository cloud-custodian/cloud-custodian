Filtering SageMaker resources on CloudWatch metrics
===================================================

The ``metrics`` filter selects SageMaker resources by their CloudWatch
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

Most resources have a single time series. Several SageMaker resources stand
in front of sub-resources and have a series for each of them.  An endpoint
has one per production variant. A job one per instance. The condition is
applied to all of the values in all of those series.

Specify ``dimensions`` to narrow a filter to particular sub-resources.

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

SageMaker jobs
--------------

Training, processing and batch transform job series carry one dimension:

``Host``
   A single instance of a single job, written ``<job-name>/algo-<n>`` for
   training and processing jobs, and ``<job-name>/<instance-id>`` for
   transform jobs, whose instance ids are EC2 instance ids that no SageMaker
   API reports. The filter finds a job's instances from CloudWatch and
   queries each of them.

To measure one instance, give its whole ``Host``:

.. code-block:: yaml

            dimensions:
              Host: my-training-job/algo-1

Jobs with under-used instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Training, processing and batch transform jobs each default to their own
namespace, so no ``namespace`` key is needed:

.. code-block:: yaml

    policies:
      - name: sagemaker-training-jobs-underused-gpu
        resource: aws.sagemaker-job
        filters:
          - type: metrics
            name: GPUUtilization
            statistics: Average
            days: 1
            period: 3600
            value: 10
            op: less-than

Job resources return in-progress jobs unless the policy says otherwise, so
this reports on jobs while they run. Add ``query: [{StatusEquals:
Completed}]`` to look at finished ones -- their instances remain findable
for two weeks.

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
   * - ``sagemaker-job``
     - ``/aws/sagemaker/TrainingJobs``
     - same
   * - ``sagemaker-processing-job``
     - ``/aws/sagemaker/ProcessingJobs``
     - same
   * - ``sagemaker-transform-job``
     - ``/aws/sagemaker/TransformJobs``
     - same

For the metric names each namespace offers, see `SageMaker metrics in
CloudWatch
<https://docs.aws.amazon.com/sagemaker/latest/dg/monitoring-cloudwatch.html>`_.
