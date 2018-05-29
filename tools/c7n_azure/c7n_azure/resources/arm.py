# Copyright 2018 Capital One Services, LLC
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

import six
from c7n_azure.query import QueryResourceManager, QueryMeta
from c7n_azure.actions import Tag, AutoTagUser, RemoveTag, TagTrim
from c7n_azure.utils import ResourceIdParser
from c7n_azure.provider import resources
from datetime import datetime, timedelta
from statistics import mean, median
from c7n.filters import Filter
from c7n_azure.metrics import Metrics


@resources.register('armresource')
@six.add_metaclass(QueryMeta)
class ArmResourceManager(QueryResourceManager):

    class resource_type(object):
        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        enum_spec = ('resources', 'list')
        id = 'id'
        name = 'name'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )

    def augment(self, resources):
        for resource in resources:
            if 'id' in resource:
                resource['resourceGroup'] = ResourceIdParser.get_resource_group(resource['id'])
        return resources

    @staticmethod
    def register_arm_specific(registry, _):
        for resource in registry.keys():
            klass = registry.get(resource)
            if issubclass(klass, ArmResourceManager):
                klass.action_registry.register('tag', Tag)
                klass.action_registry.register('untag', RemoveTag)
                klass.action_registry.register('auto-tag-user', AutoTagUser)
                klass.action_registry.register('tag-trim', TagTrim)


@ArmResourceManager.register_arm_specific.filter_registry.register('metric')
class MetricFilter(Filter):

    funcs = {
        'max': max,
        'min': min,
        'avg': mean,
        'med': median
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

        if self.op == '>=':
            return f_value >= self.threshold
        if self.op == '>':
            return f_value > self.threshold
        if self.op == '<=':
            return f_value <= self.threshold
        if self.op == '<':
            return f_value < self.threshold
        if self.op == '=':
            return f_value == self.threshold






resources.subscribe(resources.EVENT_FINAL, ArmResourceManager.register_arm_specific)
