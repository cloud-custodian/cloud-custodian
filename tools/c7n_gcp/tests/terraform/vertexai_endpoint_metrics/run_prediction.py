#!/usr/bin/env python3

import json
import os
import pickle
import sys
import tempfile
import time
import uuid
from pathlib import Path

import numpy as np
from google.cloud import aiplatform
from google.cloud import storage
from sklearn.linear_model import LinearRegression


REPO_ROOT = Path(__file__).resolve().parents[5]
TOOLS_GCP_ROOT = REPO_ROOT / "tools" / "c7n_gcp"
if str(TOOLS_GCP_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_GCP_ROOT))

from c7n_gcp.client import Session  # noqa: E402
from c7n_gcp.resources.vertexai import VertexAIEndpoint  # noqa: E402

STATE_PATH = Path(__file__).with_name("run_prediction_state.jsonl")


def append_state(**data):
    with open(STATE_PATH, "a") as fh:
        fh.write(json.dumps(data, sort_keys=True) + "\n")


def main():
    metric_type = "aiplatform.googleapis.com/prediction/online/prediction_count"

    with open(Path(__file__).with_name("tf_resources.json")) as fh:
        resources = json.load(fh)["resources"]

    endpoint = resources["google_vertex_ai_endpoint"]["default"]
    bucket = resources["google_storage_bucket"]["artifacts"]

    project_id = endpoint["project"]
    bucket_name = bucket["name"]
    location = endpoint["location"]
    endpoint_name = (
        f"projects/{project_id}/locations/{location}/endpoints/{endpoint['name']}"
    )
    uploaded_model_display_name = f"c7n-metrics-model-{uuid.uuid4().hex[:8]}"
    deployed_model_display_name = f"c7n-metrics-deploy-{uuid.uuid4().hex[:8]}"

    STATE_PATH.unlink(missing_ok=True)
    append_state(
        bucket_name=bucket_name,
        endpoint_name=endpoint_name,
        location=location,
        project_id=project_id,
    )

    session = Session(project_id=project_id)
    monitoring_client = session.client("monitoring", "v3", "projects.timeSeries")
    aiplatform.init(project=project_id, location=location, staging_bucket=f"gs://{bucket_name}")

    with tempfile.TemporaryDirectory() as temp_dir:
        model = LinearRegression()
        x_train = np.array([[1.0], [2.0], [3.0]])
        y_train = np.array([1.0, 2.0, 3.0])
        model.fit(x_train, y_train)

        model_path = os.path.join(temp_dir, "model.pkl")
        with open(model_path, "wb") as model_file:
            pickle.dump(model, model_file, protocol=4)

        artifact_prefix = f"vertexai-endpoint-metrics/{uuid.uuid4().hex}"
        storage_client = storage.Client(project=project_id)
        bucket_client = storage_client.bucket(bucket_name)
        bucket_client.blob(f"{artifact_prefix}/model.pkl").upload_from_filename(model_path)
        artifact_uri = f"gs://{bucket_name}/{artifact_prefix}"
        append_state(artifact_prefix=artifact_prefix, artifact_uri=artifact_uri)

    uploaded_model = aiplatform.Model.upload(
        display_name=uploaded_model_display_name,
        artifact_uri=artifact_uri,
        serving_container_image_uri=(
            "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-3:latest"
        ),
        sync=True,
    )
    uploaded_model_name = getattr(uploaded_model, "resource_name", None)
    if not uploaded_model_name:
        uploaded_model_name = uploaded_model._gca_resource.name
    append_state(
        uploaded_model_display_name=uploaded_model_display_name,
        uploaded_model_name=uploaded_model_name,
    )

    aiplatform_endpoint = aiplatform.Endpoint(endpoint_name=endpoint_name)
    deployed_model = uploaded_model.deploy(
        endpoint=aiplatform_endpoint,
        deployed_model_display_name=deployed_model_display_name,
        machine_type="n1-standard-2",
        min_replica_count=1,
        max_replica_count=1,
        sync=True,
    )
    assert deployed_model is not None

    endpoint_client = VertexAIEndpoint.get_location_client(
        session, location, "projects.locations.endpoints"
    )

    for _ in range(30):
        endpoint_resource = endpoint_client.execute_command("get", {"name": endpoint_name})
        if endpoint_resource.get("deployedModels"):
            break
        time.sleep(10)
    else:
        raise AssertionError("Endpoint never reported a deployed model")

    for deployed_model_resource in endpoint_resource.get("deployedModels", []):
        if deployed_model_resource.get("displayName") == deployed_model_display_name:
            append_state(
                deployed_model_display_name=deployed_model_display_name,
                deployed_model_id=deployed_model_resource.get("id"),
            )
            break

    for _ in range(3):
        prediction = aiplatform_endpoint.predict(instances=[[1.0]])
        assert prediction.predictions
        time.sleep(2)

    metric_filter = (
        f'metric.type = "{metric_type}" AND '
        f'( resource.labels.endpoint_id = "{endpoint_name.split("/")[-1]}" )'
    )
    metric_ready = False
    for _ in range(20):
        end_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        start_time = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 86400)
        )
        metric_response = monitoring_client.execute_query(
            "list",
            {
                "name": f"projects/{project_id}",
                "filter": metric_filter,
                "interval_startTime": start_time,
                "interval_endTime": end_time,
                "aggregation_alignmentPeriod": "86400s",
                "aggregation_perSeriesAligner": "ALIGN_SUM",
                "aggregation_crossSeriesReducer": "REDUCE_NONE",
                "view": "FULL",
            },
        )
        if metric_response.get("timeSeries"):
            metric_ready = True
            break
        time.sleep(30)

    assert metric_ready, "Timed out waiting for endpoint metric time series"


if __name__ == "__main__":
    main()
