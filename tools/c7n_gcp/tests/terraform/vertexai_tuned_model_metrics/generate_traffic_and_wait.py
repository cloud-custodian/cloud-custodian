#!/usr/bin/env python3
"""Send a few prediction requests to a tuned Gemini model's endpoint, then
poll Cloud Monitoring until aiplatform.googleapis.com/tuned_model/
online_serving/tokens has a data point for it. Avoids guessing a fixed
propagation delay -- see the equivalent helpers in test_vertexai.py for
the publisher-model version of this pattern.

Usage:
    python generate_traffic_and_wait.py <endpoint-resource-name>
"""
import sys
import time
from datetime import datetime, timedelta, timezone

import google.auth
import requests
from google.auth.transport.requests import AuthorizedSession

LOCATION = "us-central1"
METRIC_TYPE = "aiplatform.googleapis.com/tuned_model/online_serving/tokens"


def generate_traffic(session, endpoint, calls=5):
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/{endpoint}:generateContent"
    body = {"contents": [{"role": "user", "parts": [{"text": "What is the capital of Chile?"}]}]}
    for _ in range(calls):
        resp = session.post(url, json=body, timeout=30)
        resp.raise_for_status()


def wait_for_metric(session, project_id, endpoint_id, timeout=1800, interval=30):
    url = f"https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries"
    deadline = time.time() + timeout
    while True:
        # Recompute the window every poll. A window fixed before the loop
        # ends in the past, and the point this waits for lands after it.
        now = datetime.now(timezone.utc).replace(microsecond=0)
        params = {
            "filter": (
                f'metric.type = "{METRIC_TYPE}" AND '
                f'resource.labels.endpoint_id = "{endpoint_id}"'
            ),
            "interval.startTime": (now - timedelta(hours=6)).isoformat(),
            "interval.endTime": now.isoformat(),
            "view": "FULL",
        }
        try:
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"poll failed, retrying: {e}", file=sys.stderr)
            if time.time() >= deadline:
                raise
            time.sleep(interval)
            continue
        if resp.json().get("timeSeries"):
            return
        if time.time() >= deadline:
            raise TimeoutError(
                f"{METRIC_TYPE} did not appear for endpoint {endpoint_id} "
                f"within {timeout}s of polling")
        time.sleep(interval)


def main():
    endpoint = sys.argv[1]
    endpoint_id = endpoint.rsplit("/", 1)[-1]

    credentials, project_id = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)

    generate_traffic(session, endpoint)
    print("traffic sent, polling for metric...", file=sys.stderr)
    wait_for_metric(session, project_id, endpoint_id)
    print("metric appeared", file=sys.stderr)


if __name__ == "__main__":
    main()
