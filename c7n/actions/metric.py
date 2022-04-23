# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
import jmespath

from .core import BaseAction
from c7n.manager import resources
from c7n import utils


def average(numbers):
    return float(sum(numbers)) / max(len(numbers), 1)


def distinct_count(values):
    return float(len(set(values)))


METRIC_OPS = {
    'count': len,
    'distinct_count': distinct_count,
    'sum': sum,
    'average': average,
}

METRIC_UNITS = [
    # Time
    'Seconds',
    'Microseconds',
    'Milliseconds',
    # Bytes and Bits
    'Bytes',
    'Kilobytes',
    'Megabytes',
    'Gigabytes',
    'Terabytes',
    'Bits',
    'Kilobits',
    'Megabits',
    'Gigabits',
    'Terabits',
    # Rates
    'Bytes/Second',
    'Kilobytes/Second',
    'Megabytes/Second',
    'Gigabytes/Second',
    'Terabytes/Second',
    'Bits/Second',
    'Kilobits/Second',
    'Megabits/Second',
    'Gigabits/Second',
    'Terabits/Second',
    'Count/Second',
    # Other Scalars
    'Percent',
    'Count',
    'None'
]


class PutMetric(BaseAction):
    """Action to put metrics based on an expression into CloudWatch metrics

    :example:

    .. code-block:: yaml

            policies:
              - name: track-attached-ebs
                resource: ec2
                comment: |
                  Put the count of the number of EBS attached disks to an instance
                filters:
                  - Name: tracked-ec2-instance
                actions:
                  - type: put-metric
                    key: Reservations[].Instances[].BlockDeviceMappings[].DeviceName
                    namespace: Usage Metrics
                    metric_name: Attached Disks
                    op: count
                    units: Count

    op and units are optional and will default to simple Counts.
    """
    # permissions are typically lowercase servicename:TitleCaseActionName
    permissions = {'cloudwatch:PutMetricData', }
    schema_alias = True
    schema = {
        'type': 'object',
        'required': ['type', 'key', 'namespace', 'metric_name'],
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['put-metric', ]},
            'key': {'type': 'string'},  # jmes path
            'namespace': {'type': 'string'},
            'metric_name': {'type': 'string'},
            'dimensions': {
                'type': 'array',
                'items': {'type': 'object'},
            },
            'op': {'enum': list(METRIC_OPS.keys())},
            'units': {'enum': METRIC_UNITS}
        }
    }

    def process(self, resources):
        ns = self.data['namespace']
        metric_name = self.data['metric_name']
        key_expression = self.data.get('key', 'Resources[]')
        operation = self.data.get('op', 'count')
        units = self.data.get('units', 'Count')
        # dimensions are passed as a list of dicts
        dimensions = self.data.get('dimensions', [])

        now = datetime.utcnow()

        # reduce the resources by the key expression, and apply the operation to derive the value
        values = []
        self.log.debug("searching for %s in %s", key_expression, resources)
        try:
            values = jmespath.search("Resources[]." + key_expression,
                                     {'Resources': resources})
            # I had to wrap resourses in a dict like this in order to not have jmespath expressions
            # start with [] in the yaml files.  It fails to parse otherwise.
        except TypeError as oops:
            self.log.error(oops.message)

        value = 0
        try:
            f = METRIC_OPS[operation]
            value = f(values)
        except KeyError:
            self.log.error("Bad op for put-metric action: %s", operation)

        # for demo purposes
        # from math import sin, pi
        # value = sin((now.minute * 6 * 4 * pi) / 180) * ((now.hour + 1) * 4.0)

        metrics_data = [
            {
                'MetricName': metric_name,
                'Dimensions': [{'Name': i[0], 'Value': i[1]}
                               for d in dimensions
                               for i in d.items()],
                'Timestamp': now,
                'Value': value,
                # TODO: support an operation of 'stats' to include this
                # structure instead of a single Value
                # Value and StatisticValues are mutually exclusive.
                # 'StatisticValues': {
                #     'SampleCount': 1,
                #     'Sum': 123.0,
                #     'Minimum': 123.0,
                #     'Maximum': 123.0
                # },
                'Unit': units,
            },
        ]

        client = utils.local_session(
            self.manager.session_factory).client('cloudwatch')
        client.put_metric_data(Namespace=ns, MetricData=metrics_data)

        return resources

    @classmethod
    def register_resources(cls, registry, resource_class):
        if 'put-metric' not in resource_class.action_registry:
            resource_class.action_registry.register('put-metric', PutMetric)


resources.subscribe(PutMetric.register_resources)
