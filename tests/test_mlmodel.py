# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestMLModel(BaseTest):

    def test_ml_deprecated(self):
        factory = self.replay_flight_data("test_ml_depecrated")
        p = self.load_policy(
            {"name": "get-ml-model", "resource": "ml-model"},
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_query_models(self):
        factory = self.replay_flight_data("test_ml_model_query")
        p = self.load_policy(
            {"name": "get-ml-model", "resource": "ml-model"}, session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], "test-delete-model")

    def test_delete_models(self):
        factory = self.replay_flight_data("test_ml_model_delete")
        p = self.load_policy(
            {
                "name": "delete-ml-model",
                "resource": "ml-model",
                "filters": [{"Status": "INPROGRESS"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], "test-delete-model")
        client = factory().client("machinelearning")
        remainder = client.describe_ml_models()["Results"]
        self.assertEqual(len(remainder), 0)
