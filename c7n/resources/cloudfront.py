# Copyright 2016 Capital One Services, LLC
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
from c7n.filters import MetricsFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('distribution')
class Distribution(QueryResourceManager):

    class resource_type(object):
        service = 'cloudfront'
        enum_spec = ('list_distributions', 'DistributionList.Items', None)
        id = 'Id'
        name = 'DomainName'
        date = 'LastModifiedTime'
        dimension = "DistributionId"


@resources.register('streaming-distribution')
class StreamingDistribution(QueryResourceManager):

    class resource_type(object):
        service = 'cloudfront'
        enum_spec = ('list_streaming_distributions', 
                     'StreamingDistributionList.Items', 
                     None)
        id = 'Id'
        name = 'DomainName'
        date = 'LastModifiedTime'
        dimension = "DistributionId"


@Distribution.filter_registry.register('metrics')
@StreamingDistribution.filter_registry.register('metrics')
class DistributionMetrics(MetricsFilter):

    def get_dimensions(self, resource):
        return [{'Name': self.model.dimension,
                 'Value': resource[self.model.id]},
                {'Name': 'Region', 'Value': 'Global'}]

