#!/usr/bin/env python3
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
"""
Script to create and upload test models for Vertex AI tests.

This script includes validation to ensure models are compatible with the
Vertex AI serving container before deployment, preventing long deployment
failures.

Usage:
    # Create and upload models only (with validation)
    python create_test_model.py

    # Create, upload, and deploy models to endpoints
    python create_test_model.py --deploy-to-endpoints

    # Only deploy (if models already exist)
    python create_test_model.py --skip-model-upload --deploy-to-endpoints

    # Skip container validation (not recommended)
    python create_test_model.py --skip-container-validation

Validation:
    - Checks numpy version compatibility (must be < 2.0)
    - Tests model loading locally
    - Tests model in actual Vertex AI container (requires Docker)
"""

# Standard library imports
import json
import logging
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Third-party imports
import click
import numpy as np
import yaml
from sklearn.linear_model import LinearRegression

log = logging.getLogger('c7n_gcp.test_setup')

# ==========================
# TEST ENV CONFIG (EDIT HERE)
# ==========================

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
if not PROJECT:
    raise RuntimeError("GOOGLE_CLOUD_PROJECT environment variable must be set")

BUCKET = f"{PROJECT}-vertex-test-models"

REGIONS = ["us-central1", "us-east1"]

DISPLAY_NAME = "c7n-test-sklearn-model"
CONTAINER = "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-3:latest"
GCS_PREFIX = "vertex-test-models"

# Endpoint configuration (matches terraform/vertexai_endpoint/main.tf)
ENDPOINT_DISPLAY_NAMES = {
    "us-central1": "c7n-endpoint-central",
    "us-east1": "c7n-endpoint-east"
}


# ==========================
# MODEL CREATION
# ==========================

def create_trivial_model():
    """Create a simple linear regression model for testing."""
    model = LinearRegression()
    X = np.array([[1], [2], [3]])
    y = np.array([1, 2, 3])
    model.fit(X, y)
    return model


# ==========================
# VALIDATION FUNCTIONS
# ==========================

def validate_environment():
    """Validate that the environment is compatible with Vertex AI sklearn container."""
    log.info("Validating environment...")

    numpy_version = np.__version__
    log.info(f"  numpy version: {numpy_version}")

    if numpy_version.startswith('2.'):
        log.error("")
        log.error("=" * 60)
        log.error("❌ VALIDATION FAILED: Incompatible numpy version")
        log.error("=" * 60)
        log.error("")
        log.error("You are using numpy 2.x, but the Vertex AI sklearn container")
        log.error("(sklearn-cpu.1-3) uses numpy 1.x.")
        log.error("")
        log.error("This will cause deployment to fail with:")
        log.error("  ModuleNotFoundError: No module named 'numpy._core'")
        log.error("")
        log.error("To fix:")
        log.error("  1. Downgrade numpy: uv pip install 'numpy<2.0'")
        log.error("  2. Re-run this script")
        log.error("")
        sys.exit(1)

    log.info("  ✓ numpy version compatible (< 2.0)")

    try:
        import sklearn
        log.info(f"  sklearn version: {sklearn.__version__}")
        log.info("  ✓ sklearn installed")
    except ImportError:
        log.error("  ✗ sklearn not installed")
        sys.exit(1)

    log.info("✓ Environment validation passed")
    log.info("")


def validate_model_local(model_path):
    """Validate that the model can be loaded locally."""
    log.info("Validating model artifact (local environment)...")

    # Try to load the model
    try:
        with open(model_path, 'rb') as f:
            loaded_model = pickle.load(f)
        log.info(f"  ✓ Model loaded successfully: {type(loaded_model).__name__}")
    except Exception as e:
        log.error(f"  ✗ Failed to load model: {e}")
        sys.exit(1)

    # Try to make a prediction
    try:
        test_input = np.array([[1.0]])
        prediction = loaded_model.predict(test_input)
        log.info(f"  ✓ Prediction successful: {prediction}")
    except Exception as e:
        log.error(f"  ✗ Prediction failed: {e}")
        sys.exit(1)

    log.info("✓ Local validation passed")
    log.info("")


def validate_model_with_container(model_path):
    """Validate model using the actual Vertex AI container image.

    This is the most reliable validation as it uses the exact same
    environment that will be used in production.
    """
    log.info("Validating model with Vertex AI container...")
    log.info(f"  Container: {CONTAINER}")

    # Check if docker is available
    try:
        result = subprocess.run(
            ['docker', '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        log.info(f"  Docker: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        log.warning("  ⚠ Docker not available - skipping container validation")
        log.warning("  Note: This validation is recommended to catch library conflicts")
        log.info("")
        return

    # Pull the container image
    log.info("  Pulling container image (may take a few minutes)...")
    try:
        subprocess.run(
            ['docker', 'pull', CONTAINER],
            check=True,
            capture_output=True
        )
        log.info("  ✓ Container image pulled")
    except subprocess.CalledProcessError as e:
        log.warning(f"  ⚠ Failed to pull container: {e}")
        log.warning("  Skipping container validation")
        log.info("")
        return

    # Create test script
    test_script = '''
import pickle
import sys

try:
    print("Loading model...")
    with open('/model/model.pkl', 'rb') as f:
        model = pickle.load(f)
    print(f"✓ Model loaded: {type(model).__name__}")

    print("Testing prediction...")
    import numpy as np
    test_input = np.array([[1.0]])
    prediction = model.predict(test_input)
    print(f"✓ Prediction successful: {prediction}")

    print("\\n✅ CONTAINER VALIDATION PASSED")
    sys.exit(0)

except Exception as e:
    print(f"\\n❌ CONTAINER VALIDATION FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
'''

    # Create temporary directory with model and test script
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Copy model
        shutil.copy(model_path, temp_path / 'model.pkl')

        # Write test script
        (temp_path / 'test_model.py').write_text(test_script)

        # Run validation in container
        log.info("  Running validation in container...")
        try:
            result = subprocess.run(
                [
                    'docker', 'run', '--rm',
                    '--entrypoint', 'python',
                    '-v', f'{temp_path}:/model',
                    CONTAINER,
                    '/model/test_model.py'
                ],
                capture_output=True,
                text=True,
                check=True
            )

            # Show container output
            for line in result.stdout.strip().split('\n'):
                log.info(f"    {line}")

            log.info("✓ Container validation passed")
            log.info("")

        except subprocess.CalledProcessError as e:
            log.error("")
            log.error("=" * 60)
            log.error("❌ CONTAINER VALIDATION FAILED")
            log.error("=" * 60)
            log.error("")
            log.error("The model failed to load in the Vertex AI container.")
            log.error("This means deployment will fail.")
            log.error("")

            # Show both stdout and stderr
            if e.stdout and e.stdout.strip():
                log.error("Container stdout:")
                for line in e.stdout.strip().split('\n'):
                    log.error(f"  {line}")

            if e.stderr and e.stderr.strip():
                log.error("Container stderr:")
                for line in e.stderr.strip().split('\n'):
                    log.error(f"  {line}")

            if not e.stdout.strip() and not e.stderr.strip():
                log.error("No output captured from container")
                log.error(f"Return code: {e.returncode}")

            log.error("")
            sys.exit(1)


# ==========================
# MODEL ARTIFACT MANAGEMENT
# ==========================

def save_model_artifact(model, output_dir):
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    model_path = path / "model.pkl"
    with open(model_path, "wb") as f:
        # Use protocol=4 for compatibility with older numpy versions in the container
        pickle.dump(model, f, protocol=4)

    log.info(f"Saved: {model_path}")
    return path


def create_instance_schema():
    """Create the instance schema for the test model.

    The test model is a simple LinearRegression with a single feature (1D input).
    The prediction request format is: {"instances": [[1.0]]}
    The individual instance format is: [1.0] (a single-element array)

    The schema must describe the INDIVIDUAL INSTANCE, not the full request.
    It must be in YAML format following OpenAPI specification.

    Returns:
        dict: The instance schema as a dictionary (will be converted to YAML)
    """
    # Schema describes a single instance: an array with one number
    schema = {
        'type': 'array',
        'items': {
            'type': 'number'
        }
    }
    return schema


def upload_schema_to_gcs():
    """Upload the instance schema to GCS for use with Model Monitoring.

    The schema must be in YAML format following OpenAPI specification.
    This is required for Model Monitoring jobs to transition from PENDING to RUNNING state.

    Returns:
        str: GCS URI of the uploaded schema
    """
    schema = create_instance_schema()
    schema_path = f'gs://{BUCKET}/schema/instance_schema.yaml'

    # Write schema to temporary YAML file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(schema, f, default_flow_style=False)
        temp_schema_path = f.name

    try:
        # Upload to GCS
        log.info(f'Uploading instance schema to {schema_path}...')
        run(['gsutil', 'cp', temp_schema_path, schema_path])
        log.info(f'✓ Schema uploaded: {schema_path}')
        log.info('')
        log.info('Schema content:')
        with open(temp_schema_path, 'r') as f:
            log.info(f.read())
        return schema_path
    finally:
        # Clean up temp file
        os.unlink(temp_schema_path)


def upload_test_schemas_to_gcs():
    """Upload test schema files for schema validation tests.

    These files are used to test error handling in the schema validation logic:
    - invalid.yaml: Invalid YAML syntax
    - list.yaml: Valid YAML but a list instead of a dict
    - no-type.yaml: Valid YAML dict but missing the 'type' field
    """
    log.info('Uploading test schema files for validation tests...')

    test_schemas = {
        'schema/invalid.yaml': 'invalid: yaml: content: [',
        'schema/list.yaml': '- item1\n- item2\n',
        'schema/no-type.yaml': 'properties:\n  field1:\n    type: string\n',
    }

    for gcs_path, content in test_schemas.items():
        full_gcs_path = f'gs://{BUCKET}/{gcs_path}'

        # Write content to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            run(['gsutil', 'cp', temp_path, full_gcs_path])
            log.info(f'  ✓ {gcs_path}')
        finally:
            os.unlink(temp_path)

    log.info('✓ Test schema files uploaded')
    log.info('')


def run(cmd):
    """Helper to run shell commands with logging."""
    log.info(f"> {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


# ==========================
# GCS AND VERTEX AI UPLOAD
# ==========================

def upload_gcs(artifact_dir: Path):
    """Upload model directory to GCS.

    Vertex AI expects a directory containing model.pkl, not a tar.gz file.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    gcs_dir = f"gs://{BUCKET}/{GCS_PREFIX}/model_{ts}/"

    # Upload the entire directory
    run(["gsutil", "-m", "cp", "-r", f"{artifact_dir}/*", gcs_dir])

    return gcs_dir


def upload_vertex(artifact_uri: str, region: str):
    run([
        "gcloud", "ai", "models", "upload",
        f"--project={PROJECT}",
        f"--region={region}",
        f"--display-name={DISPLAY_NAME}-{region}",
        f"--artifact-uri={artifact_uri}",
        f"--container-image-uri={CONTAINER}",
    ])


# ==========================
# RESOURCE LOOKUP FUNCTIONS
# ==========================

def get_model_id(region: str) -> str:
    """Get the most recently created model ID for a given region."""
    result = subprocess.run(
        [
            "gcloud", "ai", "models", "list",
            f"--project={PROJECT}",
            f"--region={region}",
            f"--filter=displayName:{DISPLAY_NAME}-{region}",
            "--sort-by=~createTime",  # Sort by createTime descending (newest first)
            "--limit=1",  # Only get the most recent one
            "--format=value(name)"
        ],
        capture_output=True,
        text=True,
        check=True
    )
    model_id = result.stdout.strip()
    if not model_id:
        raise RuntimeError(f"Model not found in region {region}")
    return model_id


def get_endpoint_id(region: str) -> str:
    """Get the endpoint ID for a given region."""
    endpoint_name = ENDPOINT_DISPLAY_NAMES[region]
    result = subprocess.run(
        [
            "gcloud", "ai", "endpoints", "list",
            f"--project={PROJECT}",
            f"--region={region}",
            f"--filter=displayName:{endpoint_name}",
            "--format=value(name)"
        ],
        capture_output=True,
        text=True,
        check=True
    )
    endpoint_id = result.stdout.strip()
    if not endpoint_id:
        raise RuntimeError(
            f"Endpoint '{endpoint_name}' not found in region {region}. "
            f"Make sure to run 'terraform apply' in "
            f"tools/c7n_gcp/tests/terraform/vertexai_endpoint/ first."
        )
    return endpoint_id


# ==========================
# ENDPOINT DEPLOYMENT
# ==========================

def deploy_model_to_endpoint(region: str):
    """Deploy the model to the endpoint in the given region.

    This function is designed to be called in parallel for multiple regions.
    """
    log.info(f"[{region}] Starting deployment...")

    model_id = get_model_id(region)
    endpoint_id = get_endpoint_id(region)

    log.info(f"[{region}] Model ID: {model_id}")
    log.info(f"[{region}] Endpoint ID: {endpoint_id}")

    # Deploy model to endpoint
    cmd = [
        "gcloud", "ai", "endpoints", "deploy-model", endpoint_id,
        f"--project={PROJECT}",
        f"--region={region}",
        f"--model={model_id}",
        f"--display-name=c7n-test-deployment-{region}",
        "--machine-type=n1-standard-2",
        "--min-replica-count=1",
        "--max-replica-count=1",
        "--traffic-split=0=100"
    ]

    log.info(f"[{region}] Running: {' '.join(cmd)}")

    # Run deployment (this will block for 20-30 minutes)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        log.error(f"[{region}] Deployment failed!")
        log.error(f"[{region}] stderr: {result.stderr}")
        raise RuntimeError(f"Deployment to {region} failed: {result.stderr}")

    log.info(f"[{region}] ✅ Deployment completed successfully!")


def check_deployment_status(region: str):
    """Check if a model is already deployed to the endpoint."""
    try:
        endpoint_id = get_endpoint_id(region)
        result = subprocess.run(
            [
                "gcloud", "ai", "endpoints", "describe", endpoint_id,
                f"--project={PROJECT}",
                f"--region={region}",
                "--format=json"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        endpoint_data = json.loads(result.stdout)
        deployed_models = endpoint_data.get("deployedModels", [])
        return len(deployed_models) > 0
    except Exception:
        return False


# ==========================
# MAIN ENTRY POINT
# ==========================

@click.command()
@click.option(
    '--deploy-to-endpoints',
    is_flag=True,
    help='Deploy models to endpoints after uploading (requires endpoints to exist)'
)
@click.option(
    '--skip-model-upload',
    is_flag=True,
    help='Skip model creation/upload and only deploy to endpoints'
)
@click.option(
    '--skip-container-validation',
    is_flag=True,
    help='Skip Docker container validation (not recommended)'
)
def main(deploy_to_endpoints, skip_model_upload, skip_container_validation):
    """Create and upload test models for Vertex AI tests."""
    logging.basicConfig(level=logging.INFO)

    log.info(f"Project: {PROJECT}")
    log.info(f"Bucket: {BUCKET}")
    log.info(f"Regions: {REGIONS}")
    log.info("")

    # Validate environment before doing anything
    validate_environment()

    # Always upload test schemas (they're small and needed for tests)
    log.info("Uploading test schemas for validation tests...")
    upload_test_schemas_to_gcs()

    if not skip_model_upload:
        log.info("Creating model...")
        model = create_trivial_model()

        log.info("Saving artifact to current directory...")
        artifact_dir = save_model_artifact(model, ".")

        # Validate the saved model
        model_path = artifact_dir / "model.pkl"
        validate_model_local(model_path)

        if not skip_container_validation:
            validate_model_with_container(model_path)
        else:
            log.warning("⚠ Skipping container validation (not recommended)")
            log.warning("  The model may fail during deployment due to library conflicts")
            log.info("")

        log.info("Uploading to GCS...")
        gcs_uri = upload_gcs(artifact_dir)

        log.info("Uploading instance schema for Model Monitoring...")
        schema_uri = upload_schema_to_gcs()

        log.info("Uploading to Vertex Model Registry (parallel)...")
        log.info("")

        # Upload models to all regions in parallel
        with ThreadPoolExecutor(max_workers=len(REGIONS)) as executor:
            # Submit model upload tasks for each region
            model_futures = {
                executor.submit(upload_vertex, gcs_uri, region): region
                for region in REGIONS
            }

            # Wait for model uploads to complete
            for future in as_completed(model_futures):
                region = model_futures[future]
                try:
                    future.result()
                    log.info(f"✅ Model uploaded to {region}")
                except Exception as e:
                    log.error(f"❌ Model upload to {region} failed: {e}")
                    raise

        log.info("")
        log.info("✅ DONE — Models and schema uploaded.")
        log.info(f"Model artifact URI: {gcs_uri}")
        log.info(f"Instance schema URI: {schema_uri}")
        log.info("")
        log.info("The schema URI can be used with Model Monitoring to avoid PENDING state:")
        log.info(f"  analysis_instance_schema_uri: {schema_uri}")

    else:
        log.info("Skipping model creation/upload...")
        log.info("")

    if deploy_to_endpoints:
        log.info("")
        log.info("Checking deployment status...")
        log.info("")

        # Check which regions need deployment
        regions_to_deploy = []
        for region in REGIONS:
            if check_deployment_status(region):
                log.info(f"✓ {region}: Model already deployed, skipping")
            else:
                log.info(f"⚬ {region}: Needs deployment")
                regions_to_deploy.append(region)

        if not regions_to_deploy:
            log.info("")
            log.info("=" * 60)
            log.info("✅ ALL MODELS ALREADY DEPLOYED")
            log.info("=" * 60)
            log.info("")
            log.info("All regions already have deployed models!")
            log.info("Endpoints are ready for monitoring job tests.")
        else:
            # Deploy to all regions in parallel
            log.info("")
            log.info("=" * 60)
            log.info("DEPLOYING MODELS TO ENDPOINTS (PARALLEL)")
            log.info("=" * 60)
            log.info("")
            log.info(f"Deploying to: {', '.join(regions_to_deploy)}")
            log.info("Running deployments simultaneously to save time...")
            log.info("This will take approximately 20-30 minutes for first deployment.")
            log.info("")

            with ThreadPoolExecutor(max_workers=len(regions_to_deploy)) as executor:
                # Submit all deployment tasks
                future_to_region = {
                    executor.submit(deploy_model_to_endpoint, region): region
                    for region in regions_to_deploy
                }

                # Wait for all deployments to complete
                for future in as_completed(future_to_region):
                    region = future_to_region[future]
                    try:
                        future.result()
                        log.info(f"✅ {region} deployment completed successfully")
                    except Exception as e:
                        log.error(f"❌ {region} deployment failed: {e}")

            log.info("")
            log.info("=" * 60)
            log.info("✅ DEPLOYMENT COMPLETE")
            log.info("=" * 60)
            log.info("")
            log.info("Endpoints are now ready for monitoring job tests!")
            log.info("Note: Models may take a few more minutes to become fully operational.")
    else:
        log.info("")
        log.info("To deploy models to endpoints, run:")
        log.info("  python create_test_model.py --deploy-to-endpoints")
        log.info("")
        log.info("Or to only deploy (if models already exist):")
        log.info("  python create_test_model.py --skip-model-upload --deploy-to-endpoints")


if __name__ == "__main__":
    main()
