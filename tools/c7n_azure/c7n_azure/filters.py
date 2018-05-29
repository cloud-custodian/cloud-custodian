from datetime import datetime, timedelta

from c7n_azure.metrics import Metrics

from c7n.filters import Filter


def mean(numbers):
    total = 0.0
    count = 0.0
    for n in numbers:
        total += n
        count += 1
    return total / count


class MetricFilter(Filter):

    funcs = {
        'max': max,
        'min': min,
        'avg': mean
    }

    def validate(self):
        self.metric = self.data.get('metric')
        self.func = self.funcs[self.data.get('func', 'avg')]
        self.op = self.data.get('op')
        self.threshold = self.data.get('threshold')
        if not self.metric or not self.op or not self.threshold:
            raise ValueError('Need to define a metric, an operator and a threshold')
        self.threshold = float(self.threshold)
        self.timeframe = float(self.data.get('timeframe', 24))
        self.client = self.manager.get_client('azure.mgmt.monitor.MonitorManagementClient')

    def __call__(self, resource):

        m = Metrics(self.client, resource['id'])
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=self.timeframe)
        m_data = m.metric_data(metric=self.metric, start_time=start_time, end_time=end_time)
        values = [item['value'] for item in m_data[self.metric]]
        f_value = self.func(values)

        if self.op == 'ge':
            return f_value >= self.threshold
        if self.op == 'gt':
            return f_value > self.threshold
        if self.op == 'le':
            return f_value <= self.threshold
        if self.op == 'lt':
            return f_value < self.threshold
        if self.op == 'eq':
            return f_value == self.threshold
