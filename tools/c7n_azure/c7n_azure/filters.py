# Copyright 2015-2018 Capital One Services, LLC
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
from datetime import timedelta
from c7n.filters import Filter
from c7n_azure.utils import Math


class MetricFilter(Filter):

    '''
    Available intervals
    PT1M, PT5M, PT15M, PT30M, PT1H, PT6H, PT12H, P1D

    Available aggregations
    Total, Average
    '''

    DEFAULT_TIMEFRAME = 24
    DEFAULT_INTERVAL = 'P1D' # 1 Day is the largest possible interval
    DEFAULT_AGGREGATION = 'Average' # Average, Total

    aggregation_funcs = {
        'Average': Math.mean,
        'Total': Math.sum
    }

    def __init__(self, data, manager=None):
        super(MetricFilter, self).__init__(data, manager)
        # Metric name as defined by Azure SDK
        self.metric = self.data.get('metric')        
        # gt (>), ge (>=), eq (==), le (<=), lt (<)
        self.op = self.data.get('op')
        # Value to compare metric value with self.op
        self.threshold = self.data.get('threshold')
        # Number of hours from current UTC time 
        self.timeframe = float(self.data.get('timeframe', self.DEFAULT_TIMEFRAME))
        # Interval as defined by Azure SDK
        self.interval = self.data.get('interval', self.DEFAULT_INTERVAL)
        # Aggregation as defined by Azure SDK
        self.aggregation = self.data.get('aggregation', self.DEFAULT_AGGREGATION)
        # Aggregation function to be used locally
        self.func = self.aggregation_funcs[self.aggregation]

        # Give appropriate error messages for missing information
        if self.metric is None:
            raise ValueError("Need to define a metric")
        if self.func is None:
            raise ValueError("Need to define a func (avg, min, max)")
        if self.op is None:
            raise ValueError("Need to define an opeartor (gt, ge, eq, le, lt)")
        if self.threshold is None:
            raise ValueError("Need to define a threshold")
        
        # Make threshold a float
        self.threshold = float(self.threshold)
        
        # Import utcnow function as it may have been overridden for testing purposes
        from c7n_azure.actions import utcnow
        
        # Get timespan
        end_time = utcnow()
        start_time = end_time - timedelta(hours=self.timeframe)
        self.timespan = "{}/{}".format(start_time, end_time)

        # Create Azure Monitor client
        self.client = self.manager.get_client('azure.mgmt.monitor.MonitorManagementClient')

    def get_metric_data(self, resource):
        metrics_data = self.client.metrics.list(
            resource['id'],
            timespan=self.timespan,
            interval=self.interval,
            metric=self.metric,
            aggregation=self.aggregation
        )
        return [item.total for item in metrics_data.value[0].timeseries[0].data]

    def __call__(self, resource):

        m_data = self.get_metric_data(resource)
        aggregate_value = self.func(m_data)

        if self.op == 'ge':
            return aggregate_value >= self.threshold
        if self.op == 'gt':
            return aggregate_value > self.threshold
        if self.op == 'le':
            return aggregate_value <= self.threshold
        if self.op == 'lt':
            return aggregate_value < self.threshold
        if self.op == 'eq':
            return aggregate_value == self.threshold
