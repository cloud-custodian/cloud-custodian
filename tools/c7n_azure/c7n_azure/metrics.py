# Copyright 2017-2018 Capital One Services, LLC
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

from datetime import datetime, timedelta


class Metrics(object):

    def __init__(self, client, resource_id):
        self.client = client
        # Trim slash if it leads the resource_id
        if resource_id[0] == '/':
            resource_id = resource_id[1:]
        self.resource_id = resource_id

    '''
    If no metric is specified, returns object for all metrics
    available to resource. Schema:
    {
        'Metric 1 (unit value)': [
            {
                'time_stamp': (datetime for timestamp),
                'total': (measurement of unit)
            },
            {
                'time_stamp': (datetime for timestamp),
                'total': (measurement of unit)
            },
        ],
        'Metric 2 (unit value)': [
            ...
        ],
        ...
    }
    If no timespan is specified, defaults to last 24 hours
    '''
    def metric_data(self, start_time=None, end_time=None,
                interval=None, metric=None, aggregation=None):

        result = {}

        if not start_time and not end_time:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)

        if not metric:
            metrics = [m['id'] for m in self.available_metrics()]
        else:
            metrics = [metric]

        for metric in metrics:

            metrics_data = self.client.metrics.list(
                self.resource_id,
                timespan="{}/{}".format(start_time, end_time),
                interval=interval,
                metric=metric,
                aggregation=aggregation
            )

            for item in metrics_data.value:
                data_points = []
                for series in item.timeseries:
                    for data in series.data:
                        data_points.append({
                            'time_stamp': data.time_stamp,
                            'value': data.total
                        })
                # result["{} ({})".format(item.name.localized_value, item.unit.name)] = data_points
                result[item.name.localized_value] = data_points

        return result

    def available_metrics(self):
        available_metrics = []
        for metric in self.client.metric_definitions.list(self.resource_id):
            available_metrics.append({
                'name': metric.name.localized_value,
                'id': metric.name.value,
                'unit': metric.unit
            })
        return available_metrics
