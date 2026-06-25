from datetime import datetime, timezone

from c7n.reports.csvout import Formatter
from c7n.resources.chimevoice import VoiceConnector
from .apicallcaptor import ApiCallCaptor
from .common import BaseTest, event_data


class TestChimeVoice(BaseTest):
    def test_voiceconnector(self):
        # standard test runner ...
        session_factory = self.replay_flight_data('test_chimevoice_voiceconnector')

        # test data recording runner ...
        # session_factory = self.record_flight_data('test_chimevoice_voiceconnector')

        p = self.load_policy(
            {
                "name": "my-voice-policy",
                "resource": "aws.chime-voice-voiceconnector",
                'filters': [
                    {
                        "type": "value",
                        "key": "RequireEncryption",
                        "op": "ne",
                        "value": True
                    }
                ],
            },
            session_factory=session_factory,
        )

        captor = ApiCallCaptor.start_capture()

        resources = p.run()

        self.assertEqual(
            [
                {'Tags': [{'Key': 'my-key', 'Value': 'my-value'}],
                 'c7n:MatchedFilters': ['RequireEncryption'],
                 'AwsRegion': 'us-east-1',
                 'CreatedTimestamp': datetime(2024, 4, 2, 13, 4, 22, 308000, tzinfo=timezone.utc),
                 'Name': 'vc-encryption-off',
                 'OutboundHostName': 'gp9yxbfhynquklulp0dyi4.voiceconnector.chime.aws',
                 'RequireEncryption': False,
                 'UpdatedTimestamp': datetime(2024, 4, 2, 13, 35, 10, 202000, tzinfo=timezone.utc),
                 'VoiceConnectorArn':
                     'arn:aws:chime:us-east-1:644160558196:vc/gp9yxbfhynquklulp0dyi4',
                 'VoiceConnectorId': 'gp9yxbfhynquklulp0dyi4'}

            ],
            resources,
        )

        # These assertions are necessary to be sure that the "get_arns" function is correctly
        # deriving the ARN.
        # See the documentation on the "arn" field in appmesh.py.
        arns = p.resource_manager.get_arns(resources)
        self.assertEqual(
            [
                'arn:aws:chime:us-east-1:644160558196:vc/gp9yxbfhynquklulp0dyi4',
            ],
            arns,
        )

        # The "placebo" testing library doesn't allow us to make assertions
        # linking specific api's calls to the specific mock response file
        # that will serve that request. So we will compensate here by
        # making an assertion about all the api calls and the order
        # of calls that must be made.
        self.assertEqual(
            [
                {'operation': 'ListVoiceConnectors', 'params': {}, 'service': 'chime-sdk-voice'},
                {'operation': 'GetResources',
                 'params':
                     {'ResourceARNList':
                          ['arn:aws:chime:us-east-1:644160558196:vc/ddvk97wedue2gzbz8eeeri',
                           'arn:aws:chime:us-east-1:644160558196:vc/gp9yxbfhynquklulp0dyi4']},
                 'service': 'resourcegroupstaggingapi'}],
            captor.calls,
        )

    def test_chimevoice_event(self):
        session_factory = self.replay_flight_data('test_chimevoice_voiceconnector')
        p = self.load_policy(
            {

                "name": "my-voice-policy",
                "resource": "aws.chime-voice-voiceconnector",
                'filters': [
                    {
                        "type": "value",
                        "key": "RequireEncryption",
                        "op": "ne",
                        "value": True
                    }
                ],
                "mode": {
                    "type": "cloudtrail",
                    "role": "CloudCustodian",
                    "events": [
                        {
                            "source": "chime-sdk-voice.amazonaws.com",
                            "event": "CreateVoiceConnector",
                            "ids": "responseElements.voiceConnector.voiceConnectorId",
                        }
                    ],
                },
            },
            session_factory=session_factory,
        )

        # event_data() names a file in tests/data/cwe that will drive the test execution.
        # file contains an event matching that which AWS would generate in cloud trail.
        event = {
            "detail": event_data("event-chimevoice-create-voiceconnector.json"),
            "debug": True,
        }

        captor = ApiCallCaptor.start_capture()

        # RUN THE SUT
        resources = p.push(event, None)

        self.assertEqual(
            [
                {
                    'Tags': [{'Key': 'my-key', 'Value': 'my-value'}],
                    'c7n:MatchedFilters': ['RequireEncryption'],
                    'AwsRegion': 'us-east-1',
                    'CreatedTimestamp':
                        datetime(2024, 4, 2, 13, 4, 22, 308000, tzinfo=timezone.utc),
                    'Name': 'vc-encryption-off',
                    'OutboundHostName': 'gp9yxbfhynquklulp0dyi4.voiceconnector.chime.aws',
                    'RequireEncryption': False,
                    'UpdatedTimestamp':
                        datetime(2024, 4, 2, 13, 35, 10, 202000, tzinfo=timezone.utc),
                    'VoiceConnectorArn':
                        'arn:aws:chime:us-east-1:644160558196:vc/gp9yxbfhynquklulp0dyi4',
                    'VoiceConnectorId': 'gp9yxbfhynquklulp0dyi4'
                }
            ],
            resources,
        )

        # These assertions are necessary to be sure that the "get_arns" function is correctly
        # deriving the ARN.
        # See the documentation on the "arn" field in appmesh.py.
        arns = p.resource_manager.get_arns(resources)
        self.assertEqual(['arn:aws:chime:us-east-1:644160558196:vc/gp9yxbfhynquklulp0dyi4'],
                         arns)

        # The "placebo" testing library doesn't allow us to make assertions
        # linking specific api's calls to the specific mock response file
        # that will serve that request. So we will compensate here by
        # making an assertion about all the api calls and the order
        # of calls that must be made.
        self.assertEqual(
            [
                {'operation':
                     'ListVoiceConnectors', 'params': {}, 'service': 'chime-sdk-voice'},
                {'operation': 'GetResources',
                 'params':
                     {'ResourceARNList':
                          ['arn:aws:chime:us-east-1:644160558196:vc/gp9yxbfhynquklulp0dyi4']},
                 'service': 'resourcegroupstaggingapi'},
            ],
            captor.calls,
        )

    def test_reporting(self):
        f = Formatter(resource_type=VoiceConnector.resource_type)

        # provide a fake resource
        report = f.to_csv(
            records=[
                {'Tags': [{'Key': 'my-key', 'Value': 'my-value'}],
                 'c7n:MatchedFilters': ['RequireEncryption'],
                 'AwsRegion': 'us-east-1',
                 'CreatedTimestamp': datetime(2024, 4, 2, 13, 4, 22, 308000, tzinfo=timezone.utc),
                 'Name': 'vc-encryption-off',
                 'OutboundHostName': 'gp9yxbfhynquklulp0dyi4.voiceconnector.chime.aws',
                 'RequireEncryption': False,
                 'UpdatedTimestamp': datetime(2024, 4, 2, 13, 35, 10, 202000, tzinfo=timezone.utc),
                 'VoiceConnectorArn': 'arn:aws:chime:us-east-1:644160558196:vc/gp9yxbfhynquklulp0dyi4',  # noqa
                 'VoiceConnectorId': 'gp9yxbfhynquklulp0dyi4'}

            ]
        )

        # expect Formatter to inspect the definition of certain
        # fields ("name" and "date") from the AppMesh def
        # and to pick out those fields from a fake resource
        self.assertEqual([['gp9yxbfhynquklulp0dyi4',
                           'vc-encryption-off',
                           '2024-04-02 13:04:22.308000+00:00']], report)
