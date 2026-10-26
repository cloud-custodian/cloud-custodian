# Bedrock evaluation job test fixture

The AWS Terraform provider and CloudFormation cannot create a Bedrock evaluation job. This
fixture therefore uses the ephemeral-resource exception from `testing.md`: Terraform owns the
IAM role, output bucket, and lifecycle configuration, while `setup.py` and `cleanup.py` manage
only the evaluation job.

## Prerequisites and permissions

Use AWS credentials that can create, read, update, and delete the fixture's S3 bucket and
lifecycle configuration, IAM role and inline policy, and random ID. The identity must also be
able to pass the fixture role, use the Bedrock evaluation-job APIs, tag evaluation jobs, and
invoke Amazon Nova Micro in `us-east-1`. Bedrock model access must be enabled for the account.
Terraform/OpenTofu, `uv`, and the repository test dependencies must be installed.

## Recording

This fixture records in two separate phases because Terraform cannot create the evaluation job
itself. The first pytest command only provisions Terraform-managed dependencies; it does not run
test bodies and does not create flight-data recordings.

Set every `@terraform('bedrock_evaluation_job', ...)` decorator to:

```python
@terraform(
    'bedrock_evaluation_job', replay=False,
    teardown=terraform.TEARDOWN_OFF, scope='function')
```

Use function scope because session-scoped Terraform fixtures do not preserve these resources
with `TEARDOWN_OFF`. Pytest still provisions the selected evaluation-job fixtures sequentially.
Provision the dependencies without running the test bodies:

```shell
C7N_FUNCTIONAL=yes uv run pytest -s -p no:env --tf-debug --setup-only \
  tests/test_bedrock.py -k bedrock_evaluation_job
```

The setup-only run refreshes `tests/terraform/bedrock_evaluation_job/tf_resources.json` with
the live fixture outputs used by the replay-mode recording run. It also leaves temporary
Terraform states under pytest's temp directory for later destroy.

Never pass identities from the sanitized committed `tf_resources.json` to a live API. After the
setup-only run, use the just-refreshed live outputs from `tf_resources.json` to create the
evaluation job:

```shell
TF_RESOURCES="$(git rev-parse --show-toplevel)/tests/terraform/bedrock_evaluation_job/tf_resources.json" && \
jq -e '.outputs.job_name.value and .outputs.model_arn.value and .outputs.output_s3_uri.value and .outputs.role_arn.value' "$TF_RESOURCES" >/dev/null && \
uv run python tests/terraform/bedrock_evaluation_job/setup.py \
  --job-name "$(jq -r '.outputs.job_name.value' "$TF_RESOURCES")" \
  --model-arn "$(jq -r '.outputs.model_arn.value' "$TF_RESOURCES")" \
  --output-s3-uri "$(jq -r '.outputs.output_s3_uri.value' "$TF_RESOURCES")" \
  --role-arn "$(jq -r '.outputs.role_arn.value' "$TF_RESOURCES")"
```

After the setup script succeeds, temporarily switch every decorator to Terraform replay mode so
pytest uses the just-written `tf_resources.json` instead of trying to create a second fixture:

```python
@terraform('bedrock_evaluation_job', replay=True, scope='function')
```

Change each evaluation-job test to its unique `record_flight_data` call. Then run the group
without `--setup-only`; this is the step that creates or refreshes the placebo flight-data
directories:

```shell
uv run pytest -s -p no:env tests/test_bedrock.py -k bedrock_evaluation_job
```

Cleanup must happen before destroy. Delete the ephemeral job while all Terraform dependencies
still exist, and do not continue until it is deleted or confirmed absent:

```shell
TF_RESOURCES="$(git rev-parse --show-toplevel)/tests/terraform/bedrock_evaluation_job/tf_resources.json" && \
uv run python tests/terraform/bedrock_evaluation_job/cleanup.py \
  --job-name "$(jq -r '.outputs.job_name.value' "$TF_RESOURCES")"
```

Then destroy from the saved module directory with the same paths:

```shell
TF_BIN=$(command -v tofu || command -v terraform) && \
TF_MODULE_DIR="$(git rev-parse --show-toplevel)/tests/terraform/bedrock_evaluation_job" && \
find /tmp/pytest-of-"$(id -un)" -path '*/bedrock_evaluation_job*/terraform.tfstate' \
  -type f | sort | while read -r TF_STATE; do \
    TF_WORK_DIR="$(dirname "$TF_STATE")/work"; \
    TF_DATA_DIR="$TF_WORK_DIR" "$TF_BIN" -chdir="$TF_MODULE_DIR" destroy \
      -input=false -no-color -state="$TF_STATE" -auto-approve; \
  done
```

Confirm that no evaluation job, bucket, role, policy, or lifecycle configuration remains.
Convert all tests back to committed form:

```python
@terraform('bedrock_evaluation_job', scope='function')
```

Use each test's unique `replay_flight_data` call, not `record_flight_data`. Commit the regenerated
`tf_resources.json` and every refreshed or new flight-data directory after inspecting them for
credentials, unsanitized account/provider identities, and recording-only settings.

Force replay and run the entire function-scoped fixture group:

```shell
C7N_FUNCTIONAL=no uv run pytest tests/test_bedrock.py -k bedrock_evaluation_job
```

## Failure recovery

If apply, setup, recording, or any test fails, retain the printed Terraform/OpenTofu binary,
module directory, `TF_DATA_DIR`, and state path. If setup created an evaluation job, run
`cleanup.py --job-name JOB_NAME` first and confirm deletion; do not destroy the job's bucket,
role, policy, or lifecycle configuration until cleanup succeeds. Then run the exact destroy
command above from the saved module directory. Restart recording from a fresh apply rather than
reusing partial state or flight data, and never send sanitized `tf_resources.json` identities
to live APIs.
