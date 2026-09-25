#!/usr/bin/env python3
"""Delete the endpoint and tuned model created by run_tuning.py.

Best-effort for each resource: reports failures instead of raising, since
partial cleanup shouldn't block finishing the recording session.

The tuning job record itself is not deleted. The Vertex AI API has no
delete method for tuningJobs (only cancel, create, get, list, and
rebaseTunedModel), so a completed job stays listed under
`gcloud ai tuning-jobs list` indefinitely. That's expected, not a bug here.

Usage:
    python cleanup.py <tuning-job-name> <endpoint-resource-name> <model-resource-name>
"""
import sys
import time

import google.auth
from google.auth.transport.requests import AuthorizedSession

LOCATION = "us-central1"


def delete(session, resource_name, label):
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/{resource_name}"
    resp = session.delete(url, timeout=30)
    if resp.ok:
        print(f"deleted {label}: {resource_name}", file=sys.stderr)
    else:
        print(f"failed to delete {label} {resource_name}: {resp.status_code} {resp.text}",
              file=sys.stderr)


def wait_for_operation(session, operation_name, timeout=300, interval=10):
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/{operation_name}"
    deadline = time.time() + timeout
    while True:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        op = resp.json()
        if op.get("done"):
            return op
        if time.time() >= deadline:
            raise TimeoutError(f"{operation_name} did not finish within {timeout}s")
        time.sleep(interval)


def undeploy_all_models(session, endpoint):
    # An endpoint with a deployed model refuses deletion with
    # FAILED_PRECONDITION until every DeployedModel is explicitly
    # undeployed first; there's no delete-time force option.
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/{endpoint}"
    resp = session.get(url, timeout=30)
    if not resp.ok:
        print(f"failed to fetch endpoint {endpoint}, skipping undeploy: "
              f"{resp.status_code} {resp.text}", file=sys.stderr)
        return
    deployed = resp.json().get("deployedModels", [])
    for dm in deployed:
        deployed_model_id = dm["id"]
        resp = session.post(
            f"{url}:undeployModel", timeout=30,
            json={"deployedModelId": deployed_model_id})
        if not resp.ok:
            print(f"failed to undeploy model {deployed_model_id} from {endpoint}: "
                  f"{resp.status_code} {resp.text}", file=sys.stderr)
            continue
        operation = resp.json()["name"]
        wait_for_operation(session, operation)
        print(f"undeployed model {deployed_model_id} from {endpoint}", file=sys.stderr)


def delete_model(session, model):
    # A model name that carries a @version suffix, as tunedModel.model
    # does in run_tuning.py's output, isn't valid for plain models.delete:
    # the API returns "Version should not be specified in this request.
    # Use DeleteModelVersion instead." deleteVersion takes the same name,
    # with the version suffix, at a :deleteVersion-suffixed URL.
    if "@" in model:
        url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/{model}:deleteVersion"
        resp = session.delete(url, timeout=30)
        if resp.ok:
            print(f"deleted model version: {model}", file=sys.stderr)
        else:
            print(f"failed to delete model version {model}: "
                  f"{resp.status_code} {resp.text}", file=sys.stderr)
    else:
        delete(session, model, "tuned model")


def main():
    tuning_job, endpoint, model = sys.argv[1:4]

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)

    undeploy_all_models(session, endpoint)
    delete(session, endpoint, "endpoint")
    delete_model(session, model)
    print(f"tuning job {tuning_job} left in place: tuningJobs has no delete method",
          file=sys.stderr)


if __name__ == "__main__":
    main()
