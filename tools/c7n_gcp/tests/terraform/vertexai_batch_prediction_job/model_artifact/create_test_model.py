#!/usr/bin/env python3

import pickle
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import LinearRegression

# ==========================
# TEST ENV CONFIG (EDIT HERE)
# ==========================
import os

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
if not PROJECT:
    raise RuntimeError("GOOGLE_CLOUD_PROJECT environment variable must be set")

BUCKET = f"{PROJECT}-vertex-test-models"

REGIONS = ["us-central1", "us-east1"]

DISPLAY_NAME = "c7n-test-sklearn-model"
CONTAINER = "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-3:latest"
GCS_PREFIX = "vertex-test-models"


def create_trivial_model():
    model = LinearRegression()
    X = np.array([[1], [2], [3]])
    y = np.array([1, 2, 3])
    model.fit(X, y)
    return model


def save_model_artifact(model, output_dir):
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    model_path = path / "model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    print("Saved:", model_path)
    return path


def run(cmd):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)


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


def main():
    print(f"Project: {PROJECT}")
    print(f"Bucket: {BUCKET}")
    print(f"Regions: {REGIONS}")
    print()

    print("Creating model...")
    model = create_trivial_model()

    print("Saving artifact to current directory...")
    artifact_dir = save_model_artifact(model, ".")

    print("Uploading to GCS...")
    gcs_uri = upload_gcs(artifact_dir)

    print("Uploading to Vertex Model Registry...")
    for region in REGIONS:
        print(f"\nUploading to region: {region}")
        upload_vertex(gcs_uri, region)

    print("\nDONE — uploaded to both regions.")
    print(f"\nModel artifact URI: {gcs_uri}")

    # Extract model IDs from gcloud output would require parsing
    print("\nTo get the model IDs, run:")
    for region in REGIONS:
        cmd = (
            f"gcloud ai models list --region={region} "
            f"--filter='displayName:{DISPLAY_NAME}-{region}' "
            f"--format='value(name)'"
        )
        print(f"  {cmd}")


if __name__ == "__main__":
    main()
