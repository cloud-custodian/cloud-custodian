#!/usr/bin/env python3

import json
from pathlib import Path

from google.cloud import aiplatform


STATE_PATH = Path(__file__).with_name("run_prediction_state.jsonl")


def load_state():
    state = {}
    with open(STATE_PATH) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            state.update(json.loads(line))
    return state


def main():
    state = load_state()

    project_id = state.get("project_id")
    location = state.get("location")
    endpoint_name = state.get("endpoint_name")
    deployed_model_id = state.get("deployed_model_id")
    uploaded_model_name = state.get("uploaded_model_name")

    aiplatform.init(project=project_id, location=location)

    if endpoint_name and deployed_model_id:
        endpoint = aiplatform.Endpoint(
            endpoint_name=endpoint_name, project=project_id, location=location
        )
        endpoint.undeploy(deployed_model_id=deployed_model_id, sync=True)

    if uploaded_model_name:
        model = aiplatform.Model(
            model_name=uploaded_model_name, project=project_id, location=location
        )
        model.delete(sync=True)

    STATE_PATH.unlink()


if __name__ == "__main__":
    main()
