# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest, event_data

# during recording create some sample resources in AWS the
# set use a flight recorder and set the config region to wherever you want to read state from.
# this will create recording files in the placebo dir.
# session_factory = self.record_flight_data('test_appmesh_virtualgateway')
# config = Config.empty(region="eu-west-2")

# File names in the placebo directory follow the pattern <servicename>.<OperationName>_<call#>.json
# So boto3 "AppMesh.Client.describe_mesh()" becomes "appmesh.DescribeMesh"
# and the _<call#> suffix corresponds with the file to load for each call to that api.


class TestAppmeshMesh(BaseTest):
    def test_appmesh(self):
        session_factory = self.replay_flight_data('test_appmesh_mesh')
        p = self.load_policy(
            {"name": "appmesh-mesh-policy", "resource": "aws.appmesh-mesh"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]["meshName"], "m1")
        self.assertEqual(resources[1]["meshName"], "m2")

        # These assertions are necessary to be sure that the "get_arns" function is correctly
        # deriving the ARN.
        # See the documentation on the "arn" field in appmesh.py.
        arns = p.resource_manager.get_arns(resources)
        self.assertIn('arn:aws:appmesh:eu-west-2:123456789012:mesh/m1', arns)
        self.assertIn('arn:aws:appmesh:eu-west-2:123456789012:mesh/m2', arns)

    def test_appmesh_event(self):
        session_factory = self.replay_flight_data('test_appmesh_mesh_event')
        p = self.load_policy(
            {
                "name": "appmesh-mesh-policy",
                "resource": "aws.appmesh-mesh",
                "mode": {
                    "type": "cloudtrail",
                    "role": "CloudCustodian",
                    "events": [
                        {
                            "source": "appmesh.amazonaws.com",
                            "event": "CreateMesh",
                            "ids": "requestParameters.meshName",
                        }
                    ],
                },
            },
            session_factory=session_factory,
        )
        # event_data() names a file in tests/data/cwe that will drive the test execution.
        # file contains an event matching that which AWS would generate in cloud trail.
        event = {
            "detail": event_data("event-appmesh-create-mesh.json"),
            "debug": True,
        }
        resources = p.push(event, None)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["meshName"], "m1")

        # These assertions are necessary to be sure that the "get_arns" function is correctly
        # deriving the ARN.
        # See the documentation on the "arn" field in appmesh.py.
        arns = p.resource_manager.get_arns(resources)
        self.assertIn('arn:aws:appmesh:eu-west-2:123456789012:mesh/m1', arns)


class TestAppmeshVirtualGateway(BaseTest):
    def test_appmesh_virtualgateway(self):
        session_factory = self.replay_flight_data('test_appmesh_virtualgateway')

        # test data has 2 VGW but only 1 has a port of 123
        p = self.load_policy(
            {
                "name": "appmesh-gateway-policy",
                "resource": "aws.appmesh-virtual-gateway",
                "filters": [
                    {
                        "type": "value",
                        "key": "spec.listeners[0].portMapping.port",
                        "op": "eq",
                        "value": 123,
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual("m1", resources[0]["meshName"])
        self.assertEqual("g1", resources[0]["virtualGatewayName"])
        self.assertEqual(123, resources[0]["spec"]["listeners"][0]["portMapping"]["port"])

        # These assertions are necessary to be sure that the "get_arns" function is correctly
        # deriving the ARN.
        # See the documentation on the "arn" field in appmesh.py.
        arns = p.resource_manager.get_arns(resources)
        self.assertIn('arn:aws:appmesh:eu-west-2:123456789012:mesh/m1/virtualGateway/g1', arns)

    def test_appmesh_virtualgateway_event(self):
        session_factory = self.replay_flight_data('test_appmesh_virtualgateway_event')
        p = self.load_policy(
            {
                "name": "appmesh-gateway-policy",
                "resource": "aws.appmesh-virtual-gateway",
                "mode": {
                    "type": "cloudtrail",
                    "role": "CloudCustodian",
                    "events": [
                        {
                            "source": "appmesh.amazonaws.com",
                            "event": "CreateVirtualGateway",
                            "ids": "responseElements.virtualGateway.metadata.arn",
                        }
                    ],
                },
            },
            session_factory=session_factory,
        )
        event = {
            "detail": event_data("event-appmesh-create-virtual-gateway.json"),
            "debug": True,
        }
        resources = p.push(event, None)
        self.assertEqual(len(resources), 1)
        self.assertEqual("m1", resources[0]["meshName"])
        self.assertEqual("g1", resources[0]["virtualGatewayName"])
        self.assertEqual(123, resources[0]["spec"]["listeners"][0]["portMapping"]["port"])

        # These assertions are necessary to be sure that the "get_arns" function is
        # correctly deriving the ARN.
        # See the documentation on the "arn" field in appmesh.py.
        arns = p.resource_manager.get_arns(resources)
        self.assertIn('arn:aws:appmesh:eu-west-2:123456789012:mesh/m1/virtualGateway/g1', arns)
