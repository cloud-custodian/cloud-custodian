from datetime import datetime, timedelta

from c7n_azure.metrics import Metrics

from c7n.filters import Filter


def mean(numbers):
    if numbers is None:
        return None
    total = 0.0
    count = 0.0
    for n in numbers:
        if n is not None:
            total += n
            count += 1
    if count == 0:
        return None
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
        if self.metric is None:
            raise ValueError("Need to define a metric")
        if self.func is None:
            raise ValueError("Need to define a func (avg, min, max)")
        if self.op is None:
            raise ValueError("Need to define an opeartor (gt, ge, eq, le, lt)")
        if self.threshold is None:
            raise ValueError("Need to define a threshold")
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
        if f_value is None:
            f_value = 0

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
