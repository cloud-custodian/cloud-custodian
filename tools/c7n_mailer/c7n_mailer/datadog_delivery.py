# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time

from datadog import api
from datadog import initialize
from urllib.parse import urlparse, parse_qsl


class DataDogDelivery:
    DATADOG_API_KEY = 'datadog_api_key'
    DATADOG_APPLICATION_KEY = 'datadog_application_key'

    def __init__(self, config, session, logger):
        self.config = config
        self.logger = logger
        self.session = session
        self.datadog_api_key = self.config.get(self.DATADOG_API_KEY, None)
        self.datadog_application_key = self.config.get(self.DATADOG_APPLICATION_KEY, None)

        # Initialize datadog
        if self.datadog_api_key and self.datadog_application_key:
            options = {
                'api_key': self.datadog_api_key,
                'app_key': self.datadog_application_key,

            }
            initialize(**options)

    def get_datadog_message_packages(self, sqs_message):
        date_time = time.time()
        datadog_rendered_messages = []

        metric_config_map = self._get_metrics_config_to_resources_map(sqs_message)
        if not metric_config_map:
            return datadog_rendered_messages

        if sqs_message and sqs_message.get('resources', False):
            for resource in sqs_message['resources']:
                tags = [
                    'event:{}'.format(sqs_message['event']),
                    'account_id:{}'.format(sqs_message['account_id']),
                    'account:{}'.format(sqs_message['account']),
                    'region:{}'.format(sqs_message['region'])
                ]

                tags.extend(['{key}:{value}'.format(
                    key=key, value=resource[key]) for key in resource.keys()
                    if key != 'Tags'])
                if resource.get('Tags', False):
                    tags.extend(['{key}:{value}'.format(
                        key=tag['Key'], value=tag['Value']) for tag in resource['Tags']])

                for metric_config in metric_config_map:
                    datadog_rendered_messages.append({
                        "metric": metric_config['metric_name'],
                        "points": (date_time, self._get_metric_value(
                            metric_config=metric_config, tags=tags)),
                        "tags": tags
                    })

        # eg: [{'metric': 'metric_name', 'points': (date_time, value),
        # 'tags': ['tag1':'value', 'tag2':'value']}, ...]
        return datadog_rendered_messages

    def deliver_datadog_messages(self, datadog_message_packages, sqs_message):
        if len(datadog_message_packages) > 0:
            self.logger.info(
                "Sending account:{account} policy:{policy} {resource}:{quantity} to DataDog".
                format(account=sqs_message.get('account', ''),
                       policy=sqs_message['policy']['name'],
                       resource=sqs_message['policy']['resource'],
                       quantity=len(sqs_message['resources'])))

            api.Metric.send(datadog_message_packages)

    @staticmethod
    def _get_metric_value(metric_config, tags):
        metric_value = 1
        metric_value_tag = metric_config.get('metric_value_tag', 'default')
        if metric_value_tag != 'default':
            for tag in tags:
                if metric_value_tag in tag:
                    metric_value = float(tag[tag.find(":") + 1:])

        return metric_value

    @staticmethod
    def _get_metrics_config_to_resources_map(sqs_message):
        metric_config_map = []
        if sqs_message and sqs_message.get(
                'action', False) and sqs_message['action'].get('to', False):
            for to in sqs_message['action']['to']:
                if to.startswith('datadog://'):
                    parsed = urlparse(to)
                    metric_config_map.append(dict(parse_qsl(parsed.query)))
        return metric_config_map
