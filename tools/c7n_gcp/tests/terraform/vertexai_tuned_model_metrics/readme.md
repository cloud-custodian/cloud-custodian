# Vertex AI Tuned-Model Distribution Metric Recording

This fixture has no Terraform module: a supervised fine-tuning job creates
its own `Model` and `Endpoint` resources, so there's nothing to provision
ahead of time. To record either tuned-model metric test, you need to run a
real tuning job, send it a few predictions, and wait for
`aiplatform.googleapis.com/tuned_model/online_serving/tokens` to appear.

Two tests share this setup, and one recording session produces both:

- `test_vertexai_endpoint_tuned_model_tokens_metric_unreduced`, flight
  `vertexai_endpoint_tuned_model_tokens_metric`. Its policy sets no
  `group-by-fields`, so Cloud Monitoring returns the `type=input` and
  `type=output` series separately and the filter refuses the query.
- `test_vertexai_endpoint_tuned_model_tokens_metric`, flight
  `vertexai_endpoint_tuned_model_tokens_metric_reduced`. Its policy adds
  `reducer: REDUCE_SUM` with `group-by-fields:
  [resource.labels.endpoint_id]`, so the API merges those two series into
  one before the filter sees it.

Verified against the project's live metric descriptor: this metric is
`DELTA`/`DISTRIBUTION`, keyed to the `aiplatform.googleapis.com/Endpoint`
monitored resource, with a `request_type` label distinguishing `dedicated`
(paid provisioned throughput) from `shared` (default). This fixture uses
the default shared serving path, so there's no dedicated compute node to
pay for by the hour. Billing is per-token, at the tuned model's base-model
rate.

## Prerequisites

Work from the repository root, and activate the virtualenv there. If
`python` still resolves to something else afterward, you activated from a
different checkout; run `.venv/bin/python` by path instead:

```bash
source .venv/bin/activate
export PROJECT=<your-gcp-project>
```

Configure application default credentials, then attach a quota project.
The scripts authenticate through `google.auth.default()`, and without a
quota project the Vertex AI API bills the request to a shared Google
placeholder project where the service is disabled, returning
`PERMISSION_DENIED` with `reason: SERVICE_DISABLED`:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project $PROJECT
```

Install the script dependencies:

```bash
uv pip install google-cloud-storage google-auth requests
```

Confirm the base model in `run_tuning.py` (`gemini-2.5-flash` by default)
still accepts tuning jobs. Supported models change over time, and a name
that worked last quarter can stop tuning without the API saying so until
you create a job. Check the supported-models list at
https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/tuning#supported_models

The project's own tuning history confirms it for free, and a recent
`JOB_STATE_SUCCEEDED` entry on your candidate base model is stronger
evidence than the docs page:

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "x-goog-user-project: $PROJECT" \
  "https://us-central1-aiplatform.googleapis.com/v1/projects/$PROJECT/locations/us-central1/tuningJobs" \
  | python3 -c 'import json,sys; [print(j.get("state"), j.get("baseModel"), j.get("createTime")) for j in json.load(sys.stdin).get("tuningJobs", [])]'
```

Don't probe candidate names by POSTing to `tuningJobs.create`: that call
has no dry-run mode and creates a real job on every attempt.

## Recording Workflow

Run every command from the repository root. Each step finishes before the
next begins, so no breakpoints or paused test processes are involved.

1. Create the tuned model:

```bash
python tools/c7n_gcp/tests/terraform/vertexai_tuned_model_metrics/run_tuning.py \
    | tee /tmp/tuned.json
```

   This uploads `training_data.jsonl` to the project's default Vertex AI
   staging bucket, creates the tuning job, and polls until it succeeds.
   Progress goes to stderr, and the final JSON object on stdout carries
   the `tuning_job`, `endpoint`, and `model` resource names that step 4
   deletes. This fixture tuned in 16 minutes on `gemini-2.5-flash`, and
   two `gemini-2.5-flash-lite` jobs in the same project took 25 minutes.
   Duration varies with the base model and queue depth, so watch the
   printed state transitions rather than assuming a fixed time.

2. Send traffic and wait for the metric to land:

```bash
python tools/c7n_gcp/tests/terraform/vertexai_tuned_model_metrics/generate_traffic_and_wait.py \
    "$(python -c 'import json;print(json.load(open("/tmp/tuned.json"))["endpoint"])')"
```

   This sends a few `generateContent` calls to the tuned model, then polls
   Cloud Monitoring until the metric appears instead of sleeping a fixed
   guess. The sibling `publisher-model-metrics` fixture recorded
   propagation at under 2 minutes against a documented 20-30 minute
   estimate.

3. Record each flight you need. Switch that test's `replay_flight_data`
   call to `record_flight_data`, run the test alone, then switch it back:

```bash
GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/gcloud/application_default_credentials.json \
GOOGLE_CLOUD_PROJECT=$PROJECT \
pytest tools/c7n_gcp/tests/test_vertexai.py::test_vertexai_endpoint_tuned_model_tokens_metric \
    -s -p no:env
```

   `-p no:env` is the override `docs/source/developer/tests.rst`
   documents for recording live interactions. Without it, `test.env` pins
   `GOOGLE_APPLICATION_CREDENTIALS` to the dummy
   `tools/c7n_gcp/tests/data/credentials.json`, and the run fails its
   token refresh with `invalid_client: The OAuth client was not found`.
   A local `.env`, which git ignores, overrides the same variables for
   every run instead of one.

   Change one call per run. `record_flight_data` deletes its target
   directory before recording, so pointing it at a flight you didn't
   intend to re-record destroys that fixture. Both tests read the same
   endpoint, so one traffic run from step 2 covers both recordings.

4. Delete everything the tuning job created. Do this even when a recording
   fails, because the tuned model and endpoint outlive the test run:

```bash
python tools/c7n_gcp/tests/terraform/vertexai_tuned_model_metrics/cleanup.py \
    $(python -c 'import json;d=json.load(open("/tmp/tuned.json"));print(d["tuning_job"],d["endpoint"],d["model"])')
```

   Verify the endpoint is gone before you walk away:

```bash
gcloud ai endpoints list --region=us-central1 --project=$PROJECT
```

   List endpoints without a `--filter`. A tuned model's endpoint carries
   its own `displayName`, which need not match the
   `tunedModelDisplayName` passed to `tuningJobs.create`, so filtering on
   the tuned model's name reports zero items while the endpoint is still
   running and still billable.

5. Confirm the recorder scrubbed the project id, then commit the
   `tests/data/flights/<flight-name>/` directories alongside the tests:

```bash
grep -rl "$PROJECT" tools/c7n_gcp/tests/data/flights/vertexai_endpoint_tuned_model_tokens_metric*
```

   That grep should print nothing. `recorder.py` rewrites the project id
   to `cloud-custodian` as it records.

Re-recording one flight and not the other leaves each fixture holding a
different endpoint id. Every test replays its own flight, so the ids never
need to agree.
