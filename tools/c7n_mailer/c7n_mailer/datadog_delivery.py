# Copyright 2017 Capital One Services, LLC
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

import time

from datadog import initialize
from datadog import api


class DataDogDelivery(object):
    DATADOG_APPLICATION_KEY = 'datadog_application_key'
    DATADOG_API_KEY = 'datadog_api_key'

    def __init__(self, config, session, logger):
        self.config      = config
        self.logger      = logger
        self.session     = session

        # Initialize datadog
        if self.config.get(self.DATADOG_API_KEY, False) and self.config.get(self.DATADOG_APPLICATION_KEY, False):
            options = {
                'api_key': self.config[self.DATADOG_API_KEY],
                'app_key': self.config[self.DATADOG_APPLICATION_KEY]

            }
            initialize(**options)

    def get_datadog_message_packages(self, sqs_message):
        datadog_rendered_messages = []

        for resource in sqs_message['resources']:
            metric = [
                'event:{}'.format(sqs_message['event']),
                'account_id:{}'.format(sqs_message['account_id']),
                'account:{}'.format(sqs_message['account']),
                'region:{}'.format(sqs_message['region'])
            ]

            metric.extend(['{key}:{value}'.format(key=key, value=resource[key]) for key in resource.keys()])

            datadog_rendered_messages.append(metric)

        return datadog_rendered_messages

    def deliver_datadog_messages(self, datadog_message_packages, sqs_message):
        metric_name = self.get_metric_name(sqs_message=sqs_message)
        date_time = time.time()
        metrics = []
        for message in datadog_message_packages:
            metrics.append({
                "metric": metric_name,
                "points": (date_time, self.get_metric_value(sqs_message=sqs_message, message=message)),
                "tags": message
            })

        api.Metric.send(metrics)

    @staticmethod
    def get_metric_name(sqs_message):
        metric_name = None
        for action in sqs_message['policy']['actions']:
            if action['type'] == 'notify' and action.get('metric_name', None):
                metric_name = action['metric_name']

        return metric_name

    @staticmethod
    def get_metric_value(sqs_message, message):
        metric_value = 1
        metric_value_tag = 'default'
        for action in sqs_message['policy']['actions']:
            if action['type'] == 'notify' and action.get('metric_value_tag', None):
                metric_value_tag = action['metric_value_tag']

        if metric_value_tag != 'default':
            for tag in message:
                if metric_value_tag in tag:
                    metric_value = float(tag[tag.find(":")+1:])

        return metric_value
