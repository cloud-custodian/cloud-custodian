# sagemaker_job_metrics

The prerequisites for the training, processing and batch transform jobs that
`test_sagemaker_job_metrics` creates: an execution role, a bucket holding
inputs large enough that each job runs long enough to report a minute of
CloudWatch utilization metrics, and a model for the transform job.

Terraform has no resource types for SageMaker jobs, so the jobs themselves
are created by the test. `model.tar.gz` is a copy of the one in
`../sagemaker_endpoint_metrics`, which documents how it is built.
