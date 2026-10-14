# Vertex AI Test Infrastructure Setup

This document outlines the steps to set up the Vertex AI test infrastructure for functional testing.

## Overview

This infrastructure supports **two types of tests**:

### 1. Batch Prediction Job Tests (Primary)
Tests for batch prediction job operations (create, list, cancel, delete).

**Required infrastructure:**
- ✅ GCS buckets for input/output data
- ✅ Vertex AI models registered in both regions
- ✅ Test data in JSONL format
- ❌ **Endpoints NOT required** (batch jobs use models directly)

### 2. Endpoint Monitoring Tests (Optional)
Tests for endpoint monitoring job operations.

**Required infrastructure:**
- ✅ Vertex AI models registered in both regions
- ✅ **Endpoints with deployed models** (additional setup required)
- ❌ GCS buckets NOT required for monitoring tests

---

## Quick Start

**For batch prediction job tests only:**
```bash
# 1. Create model bucket
cd tools/c7n_gcp/tests/terraform/vertexai_batch_prediction_job/model_artifact
terraform init && terraform apply

# 2. Create and upload models (NO endpoint deployment)
python create_test_model.py

# 3. Run batch prediction job tests
cd /path/to/cloud-custodian
C7N_FUNCTIONAL=yes pytest tools/c7n_gcp/tests/test_vertexai.py::test_vertexai_batch_prediction_job_multi_location -xvs
```

**For endpoint monitoring tests:**
```bash
# 1. Create model bucket
cd tools/c7n_gcp/tests/terraform/vertexai_batch_prediction_job/model_artifact
terraform init && terraform apply

# 2. Create endpoints
cd ../../vertexai_endpoint
terraform init && terraform apply

# 3. Create models AND deploy to endpoints
cd ../vertexai_batch_prediction_job/model_artifact
python create_test_model.py --deploy-to-endpoints

# 4. Run endpoint monitoring tests
cd /path/to/cloud-custodian
C7N_FUNCTIONAL=yes pytest tools/c7n_gcp/tests/test_vertexai.py::test_vertexai_endpoint_monitor -xvs
```

See detailed steps below for more information.

## Prerequisites

1. **GCP Project** with billing enabled
2. **APIs Enabled:**
   ```bash
   gcloud services enable aiplatform.googleapis.com
   gcloud services enable storage.googleapis.com
   ```
3. **Authentication:**
   ```bash
   gcloud auth application-default login
   export GOOGLE_CLOUD_PROJECT=your-project-id
   ```
4. **Terraform** installed (>= 1.5)
5. **Python dependencies:**
   ```bash
   # Install with numpy < 2.0 (required for Vertex AI sklearn container compatibility)
   uv pip install google-cloud-aiplatform google-cloud-storage scikit-learn 'numpy<2.0' click
   ```
   **Important:** The Vertex AI sklearn container uses numpy 1.x. Using numpy 2.x will cause deployment failures.
6. **Docker** (optional but recommended for container validation)

## Setup Steps

### Step 1: Create the Model Storage Bucket

First, create the GCS bucket where the model artifact will be uploaded:

```bash
cd tools/c7n_gcp/tests/terraform/vertexai_batch_prediction_job/model_artifact

# Initialize Terraform
terraform init

# Create the bucket
terraform apply
```

This creates the bucket: `gs://{project-id}-vertex-test-models/`

### Step 2: Create and Upload the Test Model

Now create the sklearn model and upload it to the bucket created in Step 1:

```bash
# Still in model_artifact directory
python create_test_model.py
```

This script will:
1. **Validate environment** - Check numpy version compatibility (must be < 2.0)
2. **Create model** - Simple linear regression model: `y = 2x`
3. **Validate locally** - Test model loading and prediction in local environment
4. **Validate with container** - Test model in actual Vertex AI sklearn container (requires Docker)
5. **Upload to GCS** - Upload to `gs://{project-id}-vertex-test-models/sklearn-model/`
6. **Register in Vertex AI** - Register the model in Model Registry in us-central1 and us-east1

**Validation Features:**
- ✅ Checks numpy version before creating model (prevents deployment failures)
- ✅ Tests model loading locally
- ✅ Tests model in actual Vertex AI container using Docker (most reliable validation)
- ⚠️ If Docker is not available, container validation is skipped with a warning

**Skip container validation** (not recommended):
```bash
python create_test_model.py --skip-container-validation
```

**Note:** This is all you need for **batch prediction job tests**. The models do NOT need to be deployed to endpoints for batch prediction jobs.

#### Optional: Deploy Models to Endpoints

**Only required for endpoint monitoring tests** (e.g., `test_vertexai_endpoint_monitor`).

If you need to test endpoint-related functionality, you can deploy the models to endpoints:

```bash
# First, create the endpoints using terraform
cd tools/c7n_gcp/tests/terraform/vertexai_endpoint
terraform init
terraform apply

# Then deploy models to the endpoints
cd tools/c7n_gcp/tests/terraform/vertexai_batch_prediction_job/model_artifact
python create_test_model.py --deploy-to-endpoints
```

This will:
1. Skip model creation/upload (models already exist from previous step)
2. Find the endpoints created by terraform (`c7n-endpoint-central`, `c7n-endpoint-east`)
3. Deploy the most recently created models to those endpoints **in parallel**
4. Configure traffic split and machine types

**Note:** Model deployment takes **20-30 minutes**. Both regions deploy **simultaneously** to save time.

If models already exist and you only want to deploy them:

```bash
python create_test_model.py --skip-model-upload --deploy-to-endpoints
```

#### Script Options

The `create_test_model.py` script supports the following options:

| Option | Description |
|--------|-------------|
| `--deploy-to-endpoints` | Deploy models to endpoints after uploading (requires endpoints to exist) |
| `--skip-model-upload` | Skip model creation/upload and only deploy to endpoints |
| `--skip-container-validation` | Skip Docker container validation (not recommended) |

**Examples:**
```bash
# Create and upload models only (with validation)
python create_test_model.py

# Create, upload, and deploy to endpoints
python create_test_model.py --deploy-to-endpoints

# Only deploy existing models to endpoints
python create_test_model.py --skip-model-upload --deploy-to-endpoints

# Skip container validation (if Docker unavailable)
python create_test_model.py --skip-container-validation
```

### Step 3: Set Environment Variables (Optional)

**Note:** Environment variables are no longer required. The script now automatically retrieves model IDs.

If you need the model IDs for other purposes, you can get them with:

```bash
# Get model ID for us-central1
gcloud ai models list --region=us-central1 \
  --filter='displayName:c7n-test-sklearn-model-us-central1' \
  --format='value(name)'

# Get model ID for us-east1
gcloud ai models list --region=us-east1 \
  --filter='displayName:c7n-test-sklearn-model-us-east1' \
  --format='value(name)'
```

### Step 4: Generate Test Data if needed

Pytest terraform grabs the data from the input_data.jsonl file stored locally. If you need to generate a larger dataset to test with, run the following:

```bash
cd tools/c7n_gcp/tests/terraform/vertexai_batch_prediction_job

# Generate 100 instances (default)
python generate_test_data.py

# Or specify a custom count
python generate_test_data.py --count 50
```

This creates `input_data.jsonl` with single-feature instances matching the model's expected input format:
```json
[0.0]
[1.0]
[2.0]
...
```


### Step 5: Run the Functional Test

Now you can run the test in recording mode:

```bash
cd /path/to/cloud-custodian  # Repository root

# Run in functional/recording mode
C7N_FUNCTIONAL=yes pytest tools/c7n_gcp/tests/test_vertexai.py::test_vertexai_batch_prediction_job_multi_location -xvs
```

The test will:
1. Use terraform-managed infrastructure (buckets, data)
2. Create batch prediction jobs via API in both regions
3. Record API interactions to flight data files
4. Query the jobs using Cloud Custodian policy
5. Verify jobs are found in both regions

## File Structure

```
vertexai_batch_prediction_job/
├── vertex_batch.md              # This file
├── main.tf                      # Terraform configuration (buckets for batch jobs)
├── tf_resources.json            # Generated by terraform (outputs)
├── input_data.jsonl             # Generated test data
├── generate_test_data.py        # Script to generate test data
└── model_artifact/
    ├── create_test_model.py     # Script to create/upload models and deploy to endpoints
    └── main.tf                  # Terraform for model bucket

../vertexai_endpoint/
└── main.tf                      # Terraform for endpoints (optional, for monitoring tests)
```

## Troubleshooting

### Numpy Version Error
If you see `ModuleNotFoundError: No module named 'numpy._core'` during deployment:
- You're using numpy 2.x, but Vertex AI sklearn container uses numpy 1.x
- Fix: `uv pip install 'numpy<2.0'` and recreate the model
- The validation script will catch this before deployment

### Container Validation Failed
If Docker validation fails:
- Check the error message for specific library conflicts
- Ensure you're using compatible library versions
- If Docker is not available, you can skip validation with `--skip-container-validation` (not recommended)

### Model Not Found Error
- The script now automatically finds the most recent model
- Check models exist: `gcloud ai models list --region=us-central1`
- If multiple models exist with the same name, the most recent one is used

### Deployment Timeout
- First deployments can take 20-30 minutes
- Check deployment status in GCP Console: Vertex AI → Endpoints
- Both regions deploy in parallel to save time (total time ~20-30 minutes, not 40-60)

### Permission Errors
- Ensure service account has Vertex AI and Storage permissions
- Run: `gcloud auth application-default login`


## Cleanup

### Cleaning Up Test Batch Prediction Jobs

Batch prediction jobs created by the test are ephemeral and not managed by terraform. Use the cleanup script to delete test jobs:

```bash
# From repository root

# Clean up all jobs matching the default pattern 'c7n-test'
python tools/c7n_gcp/tests/scripts/cleanup_vertex_ai_batch_jobs.py

# Clean up jobs with a custom pattern
python tools/c7n_gcp/tests/scripts/cleanup_vertex_ai_batch_jobs.py --pattern my-test-pattern

# Clean up jobs in a specific project
python tools/c7n_gcp/tests/scripts/cleanup_vertex_ai_batch_jobs.py --project my-project-id
```

The script will:
- Search for batch prediction jobs in us-central1 and us-east1
- Cancel any running/pending jobs that match the pattern
- Delete all matching jobs
- Provide detailed logging of the cleanup process

Alternatively, you can use gcloud commands to manually delete jobs:

```bash
gcloud ai batch-prediction-jobs list --region=us-central1
gcloud ai batch-prediction-jobs delete JOB_ID --region=us-central1
```

### Cleaning Up Deployed Models (Optional)

If you deployed models to endpoints, you should undeploy them before destroying infrastructure:

```bash
# Undeploy models from endpoints
gcloud ai endpoints undeploy-model ENDPOINT_ID \
  --region=us-central1 \
  --deployed-model-id=DEPLOYED_MODEL_ID

# Or delete the entire endpoint (which also undeploys models)
gcloud ai endpoints delete ENDPOINT_ID --region=us-central1
```

### Destroying Infrastructure

To destroy all terraform-managed infrastructure:

```bash
# Destroy endpoints (if created)
cd tools/c7n_gcp/tests/terraform/vertexai_endpoint
terraform destroy

# Destroy batch job infrastructure
cd ../vertexai_batch_prediction_job
terraform destroy

# Destroy the model bucket
cd model_artifact
terraform destroy
```

**Note:** You may need to manually delete models from Vertex AI Model Registry:

```bash
gcloud ai models delete MODEL_ID --region=us-central1
gcloud ai models delete MODEL_ID --region=us-east1
```

