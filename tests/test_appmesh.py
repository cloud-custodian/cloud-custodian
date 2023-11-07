# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

from .common import BaseTest, event_data

import fnmatch
import os
import time

from c7n.exceptions import PolicyExecutionError

log = logging.getLogger('custodian.appmesh')
print("SETTING ALL DEBUG")
logging.getLogger('botocore.client').setLevel(logging.DEBUG)
logging.getLogger('botocore.endpoint').setLevel(logging.DEBUG)
logging.getLogger('botocore.parsers').setLevel(logging.DEBUG)


class TestMesh(BaseTest):
    def test_appmesh_base(self):
        session_factory = self.replay_flight_data(
            'test_appmesh_base')
        p = self.load_policy(
            {
                "name": "appmesh-mesh-policy",
                "resource": "aws.appmesh-mesh"
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]["meshName"], "m1")
        self.assertEqual(resources[1]["meshName"], "m2")

    def test_appmesh_event_base(self):
        session_factory = self.replay_flight_data('test_appmesh_event_base')
        p = self.load_policy(
            {
                "name": "appmesh-mesh-policy",
                "resource": "aws.appmesh-mesh",
                "mode": {
                    "type": "cloudtrail",
                    "role": "CloudCustodian",
                    "events": [{
                        "source": "appmesh.amazonaws.com",
                        "event": "CreateMesh",
                        "ids": "requestParameters.meshName"
                    }]
                }
            },
            session_factory=session_factory,
        )
        event = {
            "detail": event_data("event-appmesh-create-mesh.json"),
            "debug": True,
        }
        resources = p.push(event, None)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["meshName"], "m1")
