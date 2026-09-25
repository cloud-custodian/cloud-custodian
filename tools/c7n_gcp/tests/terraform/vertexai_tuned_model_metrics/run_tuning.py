#!/usr/bin/env python3
"""Create a minimal Gemini supervised fine-tuning job and wait for it to
finish, printing the resulting tuned model and endpoint resource names.

Usage:
    python run_tuning.py [--base-model gemini-2.0-flash-001]

Requires application-default credentials (`gcloud auth application-default
login`) with aiplatform.tuningJobs.create/get and storage.objects.create on
the target project's default Vertex AI staging bucket.
"""
import argparse
import json
import pathlib
import sys
import time

import google.auth
import requests
from google.auth.transport.requests import AuthorizedSession
from google.cloud import storage

LOCATION = "us-central1"
# Reuse the project's existing Vertex AI staging bucket rather than
# provisioning a new one.
STAGING_BUCKET = "cloud-ai-platform-f4ead793-49a4-4a9e-89cf-4c77b2b61452"
TRAINING_DATA_BLOB = "c7n-11097-tuning/training_data.jsonl"
# Resolved against this file so the script runs from any directory.
TRAINING_DATA_FILE = pathlib.Path(__file__).parent / "training_data.jsonl"


def upload_training_data(project_id):
    client = storage.Client(project=project_id)
    bucket = client.bucket(STAGING_BUCKET)
    blob = bucket.blob(TRAINING_DATA_BLOB)
    blob.upload_from_filename(str(TRAINING_DATA_FILE))
    return f"gs://{STAGING_BUCKET}/{TRAINING_DATA_BLOB}"


def create_tuning_job(session, project_id, base_model, training_uri):
    url = (
        f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/"
        f"{project_id}/locations/{LOCATION}/tuningJobs"
    )
    body = {
        "baseModel": base_model,
        "tunedModelDisplayName": "c7n-11097-distribution-metric-test",
        "supervisedTuningSpec": {
            "trainingDatasetUri": training_uri,
            # Without this, Vertex creates one endpoint per intermediate
            # checkpoint in addition to the final one, leaving extra
            # endpoints behind that cleanup.py doesn't know about.
            "exportLastCheckpointOnly": True,
            "hyperParameters": {
                "epochCount": "1",
                "adapterSize": "ADAPTER_SIZE_ONE",
            },
        },
    }
    resp = session.post(url, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def poll_tuning_job(session, job_name, timeout=3600, interval=30):
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/{job_name}"
    deadline = time.time() + timeout
    while True:
        # A dropped read costs the whole job otherwise: the tuning job keeps
        # running server-side, but the caller loses the endpoint name it
        # needs to use and to clean up.
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"poll failed, retrying: {e}", file=sys.stderr)
            if time.time() >= deadline:
                raise
            time.sleep(interval)
            continue
        job = resp.json()
        state = job.get("state")
        print(f"tuning job state: {state}", file=sys.stderr)
        if state == "JOB_STATE_SUCCEEDED":
            return job
        if state in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED"):
            raise RuntimeError(f"tuning job did not succeed: {json.dumps(job.get('error'))}")
        if time.time() >= deadline:
            raise TimeoutError(f"tuning job did not finish within {timeout}s")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="gemini-2.5-flash")
    args = parser.parse_args()

    credentials, project_id = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)

    training_uri = upload_training_data(project_id)
    print(f"uploaded training data to {training_uri}", file=sys.stderr)

    job = create_tuning_job(session, project_id, args.base_model, training_uri)
    print(f"created tuning job {job['name']}", file=sys.stderr)

    job = poll_tuning_job(session, job["name"])
    tuned_model = job["tunedModel"]
    print(json.dumps({
        "tuning_job": job["name"],
        "endpoint": tuned_model["endpoint"],
        "model": tuned_model["model"],
    }, indent=2))


if __name__ == "__main__":
    main()
