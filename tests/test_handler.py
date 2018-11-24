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

import json
import logging
import os

from .common import BaseTest
from c7n.policy import Policy


class HandleTest(BaseTest):

    def test_handler(self):
        level = logging.root.level
        botocore_level = logging.getLogger("botocore").level

        self.run_dir = self.change_cwd()

        def cleanup():
            logging.root.setLevel(level)
            logging.getLogger("botocore").setLevel(botocore_level)

        self.addCleanup(cleanup)
        self.change_environment(C7N_OUTPUT_DIR=self.run_dir)

        policy_execution = []

        def push(self, event, context):
            policy_execution.append((event, context))

        self.patch(Policy, "push", push)

        from c7n import handler

        self.patch(handler, "account_id", "111222333444555")

        with open(os.path.join(self.run_dir, "config.json"), "w") as fh:
            json.dump(
                {
                    "policies": [
                        {
                            "resource": "asg",
                            "name": "autoscaling",
                            "filters": [],
                            "actions": [],
                        }
                    ]
                },
                fh,
            )

        self.assertEqual(
            handler.dispatch_event({"detail": {"errorCode": "404"}}, None), None
        )
        self.assertEqual(handler.dispatch_event({"detail": {}}, None), True)
        self.assertEqual(policy_execution, [({"detail": {}, "debug": True}, None)])

        config = handler.Config.empty()
        self.assertEqual(config.assume_role, None)
        try:
            config.foobar
        except AttributeError:
            pass
        else:
            self.fail("should have raised an error")
