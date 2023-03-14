# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import unittest

from mock import patch
from mock import MagicMock

from common import SQS_MESSAGE_2
from common import SQS_MESSAGE_3

from c7n_mailer.datadog_delivery import DataDogDelivery


DATADOG_APPLICATION_KEY = "datadog_application_key"
DATADOG_API_KEY = "datadog_api_key"
MESSAGE_ANSWER = [
    [
        "Attachments:[]",
        "AvailabilityZone:us-east-1a",
        "CreatorName:peter",
        "SupportEmail:milton@initech.com",
        "VolumeId:vol-01a0e6ea6b89f0099",
        "account:core-services-dev",
        "account_id:000000000000",
        "event:None",
        "region:us-east-1",
    ]
]
DATADOG_METRIC_SQS_MESSAGE_2 = [
    {
        "metric": "EBS_volume.available.size",
        "points": (0, 1),
        "tags": [
            "Attachments:[]",
            "AvailabilityZone:us-east-1a",
            "CreatorName:peter",
            "SupportEmail:milton@initech.com",
            "VolumeId:vol-01a0e6ea6b89f0099",
            "account:core-services-dev",
            "account_id:000000000000",
            "event:None",
            "region:us-east-1",
        ],
    },
    {
        "metric": "EBS_volume.available.size",
        "points": (0, 1),
        "tags": [
            "Attachments:[]",
            "AvailabilityZone:us-east-1c",
            "CreatorName:peter",
            "Size:8",
            "SupportEmail:milton@initech.com",
            "VolumeId:vol-21a0e7ea9b19f0043",
            "account:core-services-dev",
            "account_id:000000000000",
            "event:None",
            "region:us-east-1",
        ],
    },
]
DATADOG_METRIC_SQS_MESSAGE_3 = [
    {
        "metric": "EBS_volume.available.size",
        "points": (0, 8.0),
        "tags": [
            "Attachments:[]",
            "AvailabilityZone:us-east-1c",
            "CreatorName:peter",
            "Size:8",
            "SupportEmail:milton@initech.com",
            "VolumeId:vol-21a0e7ea9b19f0043",
            "account:core-services-dev",
            "account_id:000000000000",
            "event:None",
            "region:us-east-1",
        ],
    }
]


class TestDataDogDelivery(unittest.TestCase):
    def setUp(self):
        self.config = {
            "datadog_application_key": DATADOG_APPLICATION_KEY,
            "datadog_api_key": DATADOG_API_KEY,
        }
        self.session = patch("boto3.Session")
        self.logger = MagicMock()

        self.patcher_datadog_initialize = patch("c7n_mailer.datadog_delivery.initialize")
        self.mock_datadog_initialize = self.patcher_datadog_initialize.start()

    def tearDown(self):
        self.patcher_datadog_initialize.stop()

    def test_should_initialize_datadog_with_keys_in_config(self):
        DataDogDelivery(self.config, self.session, self.logger)

        self.mock_datadog_initialize.assert_called_with(
            api_key=DATADOG_API_KEY, app_key=DATADOG_APPLICATION_KEY
        )

    def test_should_not_initialize_datadog_with_no_keys_in_config(self):
        DataDogDelivery({}, self.session, self.logger)

        self.mock_datadog_initialize.assert_not_called()

    def test_datadog_message_packages_should_return_empty_list_if_no_sqs_messages_returned(self):
        data_dog_delivery = DataDogDelivery(self.config, self.session, self.logger)

        assert data_dog_delivery.get_datadog_message_packages(None) == []

    @patch("c7n_mailer.datadog_delivery.time.time", return_value=0)
    def test_datadog_message_packages_should_return_messages(self, mock_time):
        data_dog_delivery = DataDogDelivery(self.config, self.session, self.logger)

        answer = data_dog_delivery.get_datadog_message_packages(SQS_MESSAGE_2)
        answer[0]["tags"].sort()
        answer[1]["tags"].sort()

        assert len(answer) == 2
        assert answer == DATADOG_METRIC_SQS_MESSAGE_2

    @patch("c7n_mailer.datadog_delivery.time.time", return_value=0)
    @patch("c7n_mailer.datadog_delivery.api.Metric.send")
    def test_deliver_datadog_messages_should_send_correct_metric_to_datadog(
        self, mock_datadog_api, mock_time
    ):
        datadog_delivery = DataDogDelivery(self.config, self.session, self.logger)
        datadog_message_packages = datadog_delivery.get_datadog_message_packages(SQS_MESSAGE_2)
        datadog_delivery.deliver_datadog_messages(datadog_message_packages, SQS_MESSAGE_2)

        answer = mock_datadog_api.mock_calls[0][1][0]
        answer[0]["tags"].sort()
        answer[1]["tags"].sort()

        assert answer == DATADOG_METRIC_SQS_MESSAGE_2

    @patch("c7n_mailer.datadog_delivery.time.time", return_value=0)
    @patch("c7n_mailer.datadog_delivery.api.Metric.send")
    def test_deliver_datadog_messages_should_send_correct_metric_value_to_datadog(
        self, mock_datadog_api, mock_time
    ):
        datadog_delivery = DataDogDelivery(self.config, self.session, self.logger)
        datadog_message_packages = datadog_delivery.get_datadog_message_packages(SQS_MESSAGE_3)
        datadog_delivery.deliver_datadog_messages(datadog_message_packages, SQS_MESSAGE_3)

        answer = mock_datadog_api.mock_calls[0][1][0]
        answer[0]["tags"].sort()

        assert answer == DATADOG_METRIC_SQS_MESSAGE_3

    @patch("c7n_mailer.datadog_delivery.time.time", return_value=0)
    @patch("c7n_mailer.datadog_delivery.api.Metric.send")
    def test_deliver_datadog_messages_should_not_send_metric_if_metrics_are_empty(
        self, mock_datadog_api, mock_time
    ):
        datadog_delivery = DataDogDelivery(self.config, self.session, self.logger)
        datadog_delivery.deliver_datadog_messages([], SQS_MESSAGE_3)

        mock_datadog_api.assert_not_called()
