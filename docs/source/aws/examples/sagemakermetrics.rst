Filtering SageMaker resources on CloudWatch metrics
===================================================

The ``metrics`` filter selects SageMaker endpoints and jobs by their
CloudWatch metrics: endpoints nobody is calling, GPUs barely being used,
instances that were over-provisioned for the work.

Endpoints that serve no traffic
-------------------------------

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
at all: CloudWatch has no invocation data for it, and without a stand-in
value the filter has nothing to compare and passes it over.

Endpoints with under-used GPUs
------------------------------

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
``GPUUtilization`` and ``DiskUtilization``. Don't add ``missing-value`` to a
policy like this one -- see below.

Jobs with under-used instances
------------------------------

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
Completed}]`` to look at finished ones -- their metrics stay available for
two weeks.

Adapting these policies
-----------------------

**The threshold applies to every interval, not to an average.** ``days``
sets the window and ``period`` divides it into intervals, in seconds, so
``days: 14, period: 86400`` gives fourteen daily figures and the resource
matches only if *all fourteen* satisfy ``op``. One busy day exempts a
resource from the GPU policy above. To test a single figure for the whole
window, leave ``period`` out.

**A policy covers every variant of an endpoint, and every instance of a
job.** SageMaker reports separately for each production variant and each job
instance, and the filter checks all of them: an endpoint counts as idle only
if none of its variants was invoked. A variant or instance that reports no
data for the metric is passed over, so an endpoint with one GPU variant and
one CPU variant is judged on the GPU variant alone for a GPU metric. Filter
on ``ProductionVariants`` if you need to be certain what you are measuring.

**Use ``missing-value`` for counts, not for utilization.** No
``Invocations`` datapoint means no request arrived, so ``missing-value: 0``
records a fact. No ``CPUUtilization`` datapoint means nothing was measured,
which is not the same as idle -- filling in ``0`` there claims knowledge you
don't have, and can flag a busy instance that stopped reporting. A stand-in
value also applies only to a metric with no data *at all*; intervals with no
data inside an otherwise reporting metric are simply absent.

**Add ``dimensions`` to measure one variant instead of all of them.**

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

SageMaker also reports per instance type within a variant using instance
pools (``InstanceType``), and per instance and accelerator when the endpoint
configuration enables enhanced metrics (``InstanceId``, ``AcceleratorId``).
Any of those can go in ``dimensions``.

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
