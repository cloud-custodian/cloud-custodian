# Vertex AI Endpoint Metrics Recording

This fixture creates an empty Vertex AI endpoint and a GCS bucket. To record
`test_vertexai_endpoint_metrics`, you need to deploy a simple sklearn model to
that endpoint, send a few predictions, and wait for
`aiplatform.googleapis.com/prediction/online/prediction_count` to appear.

## Prerequisites

- Application default credentials configured for the target GCP project
- Terraform already applied for this fixture
- Python dependencies installed:

```bash
uv pip install google-cloud-aiplatform google-cloud-storage scikit-learn 'numpy<2.0'
```

`numpy<2.0` matters because the Vertex AI sklearn serving container used here is
`sklearn-cpu.1-3`.

## Recording Workflow

The practical way to use this for
`tools/c7n_gcp/tests/test_vertexai.py::test_vertexai_endpoint_metrics` is:

1. Add a breakpoint at the top of `test_vertexai_endpoint_metrics`, before
   `session_factory = test.replay_flight_data(...)`.
   Add a second breakpoint at the end of the test function so cleanup can run
   before terraform teardown.
2. Start the test in record mode.
3. When the test stops at the breakpoint, run:

```bash
python tools/c7n_gcp/tests/terraform/vertexai_endpoint_metrics/run_prediction.py
```

4. Wait for the script to finish successfully. (This can take 20-30 minutes.)
5. Return to the test and continue execution.
6. When the test stops at the second breakpoint, run:

```bash
python tools/c7n_gcp/tests/terraform/vertexai_endpoint_metrics/cleanup_prediction.py
```

7. Then proceed with terraform teardown.
