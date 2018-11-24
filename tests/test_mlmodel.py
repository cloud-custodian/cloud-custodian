# Copyright 2016-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from .common import BaseTest


class TestMLModel(BaseTest):

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
