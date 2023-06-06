# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest
from c7n.utils import yaml_load


class RunServiceTest(BaseTest):
    def test_query(self):
        factory = self.replay_flight_data("gcp-cloud-run-service")
        p = self.load_policy(
            {"name": "cloud-run-svc", "resource": "gcp.cloud-run-service"},
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]["metadata"]["name"] == "hello"


    def test_filter(self):

        factory = self.replay_flight_data("gcp-cloud-run-service")
        p = self.load_policy(yaml_load(
            """
            name: ensure_gcp_instance_labels
            description: |
              Report resources without labels
            resource: gcp.cloud-run-service
            filters:
             - type: value
               key: metadata.labels."cloud.googleapis.com/location"
               value: us-central1
            """), session_factory=factory)
        resources = p.run()
        assert len(resources) == 1


class JobServiceTest(BaseTest):
    def test_query(self):
        factory = self.replay_flight_data("gcp-cloud-run-job")
        p = self.load_policy(
            {"name": "cloud-run-job", "resource": "gcp.cloud-run-job"},
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]["metadata"]["name"] == "job"
