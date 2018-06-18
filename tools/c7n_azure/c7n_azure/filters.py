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
import operator
from c7n.filters import Filter, ValueFilter, OPERATORS
from c7n_azure.utils import Math
import jmespath


class MetricFilter(Filter):

    DEFAULT_TIMEFRAME = 24
    DEFAULT_INTERVAL = 'P1D'
    DEFAULT_AGGREGATION = 'average'

    aggregation_funcs = {
        'average': Math.mean,
        'total': Math.sum
    }

    schema = {
        'type': 'object',
        'required': ['type', 'metric', 'op', 'threshold'],
        'properties': {
            'metric': {'type': 'string'},
            'op': {'enum': [
                'eq', 'equal', 'ne', 'not-equal', 'gt', 'greater-than', 'ge',
                'gte', 'le', 'lte', 'lt', 'less-than'
            ]},
            'threshold': {'type': 'number'},
            'timeframe': {'type': 'number'},
            'interval': {'enum': [
                'PT1M', 'PT5M', 'PT15M', 'PT30M', 'PT1H', 'PT6H', 'PT12H', 'P1D']},
            'aggregation': {'enum': ['total', 'average']}
        }
    }

    def __init__(self, data, manager=None):
        super(MetricFilter, self).__init__(data, manager)
        # Metric name as defined by Azure SDK
        self.metric = self.data.get('metric')
        # gt (>), ge (>=), eq (==), le (<=), lt (<)
        self.op = OPERATORS[self.data.get('op')]
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

    def process(self, resources, event=None):
        # Import utcnow function as it may have been overridden for testing purposes
        from c7n_azure.actions import utcnow

        # Get timespan
        end_time = utcnow()
        start_time = end_time - timedelta(hours=self.timeframe)
        self.timespan = "{}/{}".format(start_time, end_time)

        # Create Azure Monitor client
        self.client = self.manager.get_client('azure.mgmt.monitor.MonitorManagementClient')

        # Process each resource in a separate thread, returning all that pass filter
        with self.executor_factory(max_workers=3) as w:
            processed = list(w.map(self.process_resource, resources))
            return [item for item in processed if item is not None]

    def get_metric_data(self, resource):
        metrics_data = self.client.metrics.list(
            resource['id'],
            timespan=self.timespan,
            interval=self.interval,
            metric=self.metric,
            aggregation=self.aggregation
        )
        m = [getattr(item, self.aggregation) for item in metrics_data.value[0].timeseries[0].data]
        return m

    def passes_op_filter(self, resource):
        m_data = self.get_metric_data(resource)
        aggregate_value = self.func(m_data)
        return self.op(aggregate_value, self.threshold)

    def process_resource(self, resource):
        return resource if self.passes_op_filter(resource) else None

class AzureValueFilter(ValueFilter):

    def get_resource_value(self, k, i):
        #print(k)
        #import pdb; pdb.set_trace()
        if k.startswith('tag:'):
            import pdb; pdb.set_trace()
            tk = k.split(':', 1)[1]
            r = None
            for t in i.get("tags", []):
                if t.get('Key') == tk:
                    r = t.get('Value')
                    break
        elif k in i:
            r = i.get(k)
        elif k not in self.expr:
            self.expr[k] = jmespath.compile(k)
            r = self.expr[k].search(i)
        else:
            r = self.expr[k].search(i)
        return r
