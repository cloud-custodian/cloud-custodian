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
from aliyunsdkcms.request.v20190101.DescribeMetricListRequest import DescribeMetricListRequest
from aliyunsdkecs.request.v20140526.DescribeEipAddressesRequest import DescribeEipAddressesRequest

from c7n.utils import type_schema
from c7n_aliyun.filters.filter import AliyunEipFilter, MetricsFilter
from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo


@resources.register('eip')
class Eip(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'eip'
        enum_spec = (None, 'EipAddresses.EipAddress', None)
        id = 'AllocationId'

    def get_request(self):
        request = DescribeEipAddressesRequest()
        return request

@Eip.filter_registry.register('unused')
class AliyunEipFilter(AliyunEipFilter):
    # 查询指定地域已创建的EIP
    """Filters

       :Example:

       .. code-block:: yaml

           policies:
             - name: aliyun-eip
               resource: aliyun.eip
               filters:
                 - type: unused
    """
    # Associating：绑定中。
    # Unassociating：解绑中。
    # InUse：已分配。
    # Available：可用。
    schema = type_schema('Available')

    def get_request(self, i):
        if i['Status'] != self.data['type']:
            return False
        return i

@Eip.filter_registry.register('metrics')
class EipMetricsFilter(MetricsFilter):

    """
          1 policies:
          2   - name: aliyun-eip
          3     resource: aliyun.eip
          4     filters:
          5       - type: unused
          6       - type: metrics
          7         name: net_in.rate_percentage
          8         period: 900
          9         startTime: '2020-11-02T08:00:00Z'
         10         endTime: '2020-11-08T08:00:00Z'
         11         statistics: Average
         12         value: 0
         13         op: eq
    """
    # 网络流入带宽利用率	: net_in.rate_percentage
    # 网络流出带宽利用率	: net_out.rate_percentage
    def get_request(self, eip):
        request = DescribeMetricListRequest()
        request.set_accept_format('json')
        request.set_StartTime(self.start)
        request.set_Period(self.period)
        request.set_Namespace(self.namespace)
        request.set_MetricName(self.metric)
        return request

@Eip.filter_registry.register('bandwidth')
class BandwidthEipFilter(AliyunEipFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下的弹性IP实例是否达到最低带宽要求
            - name: aliyun-eip-bandwidth
              resource: aliyun.eip
              filters:
                - type: Bandwidth
                  value: 10
    """
    schema = type_schema(
        'bandwidth',
        **{'value': {'type': 'number'}})

    def get_request(self, i):
        if self.data['value'] < int(i['Bandwidth']):
            return False
        return i
