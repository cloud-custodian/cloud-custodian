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
import json

import jmespath
from aliyunsdkcms.request.v20190101.DescribeMetricListRequest import DescribeMetricListRequest
from aliyunsdkslb.request.v20140515.DescribeAccessControlListAttributeRequest import \
    DescribeAccessControlListAttributeRequest
from aliyunsdkslb.request.v20140515.DescribeAccessControlListsRequest import DescribeAccessControlListsRequest
from aliyunsdkslb.request.v20140515.DescribeHealthStatusRequest import DescribeHealthStatusRequest
from aliyunsdkslb.request.v20140515.DescribeLoadBalancerAttributeRequest import DescribeLoadBalancerAttributeRequest
from aliyunsdkslb.request.v20140515.DescribeLoadBalancersRequest import DescribeLoadBalancersRequest
from aliyunsdkecs.request.v20140526.DescribeVpcsRequest import DescribeVpcsRequest

from c7n.utils import local_session
from c7n.utils import type_schema
from c7n_aliyun.client import Session
from c7n_aliyun.filters.filter import AliyunSlbFilter, MetricsFilter, AliyunSlbListenerFilter
from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo

service = 'slb'


@resources.register('slb')
class Slb(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'slb'
        enum_spec = (None, 'LoadBalancers.LoadBalancer', None)
        id = 'LoadBalancerId'

    def get_request(self):
        request = DescribeLoadBalancersRequest()
        return request


@Slb.filter_registry.register('listener')
class AliyunSlbListener(AliyunSlbFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 负载均衡开启HTTPS监听，视为“合规”。
            - name: aliyun-slb-listener
              resource: aliyun.slb
              filters:
                - type: listener
                  value: https
    """
    schema = type_schema(
        'listener',
        **{'value': {'type': 'string'}})
    # listener_protocal_key = "ListenerPortsAndProtocal.ListenerPortAndProtocal"
    listener_protocol_key = "ListenerPortsAndProtocol.ListenerPortAndProtocol"
    filter = None

    def get_request(self, i):
        request = DescribeLoadBalancerAttributeRequest()
        request.set_accept_format('json')
        request.set_LoadBalancerId(i['LoadBalancerId'])
        response = Session.client(self, service).do_action_with_exception(request)

        string = str(response, encoding="utf-8").replace("false", "False").replace("true", "True")
        data = eval(string)
        if self.data['value'] in jmespath.search(self.listener_protocol_key, data):
            return False
        return i


@Slb.filter_registry.register('unused')
class AliyunSlbUnused(AliyunSlbFilter):
    """Filters

       :Example:

       .. code-block:: yaml

           policies:
            - name: aliyun-slb-mark-unused-for-deletion
              resource: aliyun.slb
              filters:
                - type: unused
    """
    # inactive：实例已停止，此状态的实例监听不会再转发流量。
    # active：实例运行中，实例创建后，默认状态为active。
    # locked：实例已锁定，实例已经欠费或被阿里云锁定。
    schema = type_schema('inactive')

    def get_request(self, i):
        LoadBalancerId = i['LoadBalancerId']
        # slb 查询slb下是否有ECS资源
        self.LoadBalancerId = LoadBalancerId
        request = DescribeHealthStatusRequest()
        request.set_LoadBalancerId(LoadBalancerId=self.LoadBalancerId)
        request.set_accept_format('json')
        response_str = Session.client(self, service='ecs').do_action(request)
        response_detail = json.loads(response_str)
        if len(response_detail['BackendServers']['BackendServer']) > 0:
            return None
        return i


@Slb.filter_registry.register('no-listener')
class AliyunSlbNoListener(AliyunSlbListenerFilter):
    """Filters

       :Example:

       .. code-block:: yaml

           policies:
            - name: aliyun-slb-no-listener
              resource: aliyun.slb
              filters:
                - type: no-listener
    """
    schema = type_schema('no-listener')

    def get_request(self, i):
        request = DescribeLoadBalancerAttributeRequest()
        request.set_accept_format('json')
        request.set_LoadBalancerId(i['LoadBalancerId'])
        client = local_session(
            self.manager.session_factory).client(self.manager.get_model().service)
        response = json.loads(client.do_action(request))
        ListenerPort = response.get('ListenerPorts').get('ListenerPort')
        ListenerPortsAndProtocal = response.get('ListenerPortsAndProtocal').get('ListenerPortAndProtocal')
        ListenerPortsAndProtocol = response.get('ListenerPortsAndProtocol').get('ListenerPortAndProtocol')
        BackendServers = response.get('BackendServers').get('BackendServer')
        if len(ListenerPort) == 0 and len(ListenerPortsAndProtocal) == 0 and len(ListenerPortsAndProtocol) == 0 and len(
                BackendServers) == 0:
            return i
        return False


@Slb.filter_registry.register('listener-type')
class AliyunSlbListener(AliyunSlbListenerFilter):
    """Filters

       :Example:

       .. code-block:: yaml

           policies:
            # 检测您账号下的SLB负载均衡开启HTTPS或HTTP监听视为合规，否则不合规。
            - name: aliyun-slb-listener-type
              resource: aliyun.slb
              filters:
                - type: listener-type
                  value: ["https", "http"]
    """
    schema = type_schema(
        'listener-type',
        **{'value': {'type': 'array', 'items': {'type': 'string'}}})

    def get_request(self, i):
        request = DescribeLoadBalancerAttributeRequest()
        request.set_accept_format('json')
        request.set_LoadBalancerId(i['LoadBalancerId'])
        client = local_session(
            self.manager.session_factory).client(self.manager.get_model().service)
        response = json.loads(client.do_action(request))
        ListenerPortAndProtocal = response.get('ListenerPortsAndProtocal').get('ListenerPortAndProtocal')
        if len(ListenerPortAndProtocal) == 0:
            return i
        for ListenerProtocol in ListenerPortAndProtocal:
            if ListenerProtocol in self.data['value']:
                return False
        return False


@Slb.filter_registry.register('metrics')
class SlbMetricsFilter(MetricsFilter):
    """
      1              policies:
      2                - name: aliyun-slb
      3                  resource: aliyun.slb
      4                  filters:
      6                    - type: metrics
      7                      name: InstanceTrafficTX
      8                      startTime: '2020-10-08T08:00Z'
      9                      endTime: '2020-11-09T15:30Z'
     10                      statistics: Average
     11                      value: 30000
     12                      op: less-than
    """

    def get_request(self, r):
        request = DescribeMetricListRequest()
        request.set_accept_format('json')
        request.set_StartTime(self.start)
        request.set_Period(self.period)
        dimensions = self.get_dimensions(r)
        request.set_Dimensions(dimensions)
        request.set_Namespace(self.namespace)
        request.set_MetricName(self.metric)
        return request


@Slb.filter_registry.register('address-type')
class AddressTypeSlbFilter(AliyunSlbFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 负载均衡实例未直接绑定公网IP，视为“合规”。该规则仅适用于 IPv4 协议。
            - name: aliyun-slb-address-type
              resource: aliyun.slb
              filters:
                - type: address-type
                  value: internet
    """
    # internet 公网/intranet 内网
    schema = type_schema(
        'address-type',
        **{'value': {'type': 'string'}})

    def get_request(self, i):
        if self.data['value'] != i['AddressType']:
            return False
        return i


@Slb.filter_registry.register('network-type')
class NetworkTypeSlbFilter(AliyunSlbFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 账号下负载均衡实例已关联到VPC；若您配置阈值，则关联的VpcId需存在您列出的阈值中，视为“合规”。
            - name: aliyun-slb-network-type
              resource: aliyun.slb
              filters:
                - type: network-type
                  value: vpc
    """
    schema = type_schema(
        'network-type',
        **{'value': {'type': 'string'}})

    def get_request(self, i):
        if self.data['value'] == i['NetworkType']:
            return False
        return i


@Slb.filter_registry.register('vpc-type')
class VpcSlbFilter(AliyunSlbFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下SLB负载均衡实例指定属于哪些VPC, 属于则合规，不属于则"不合规"。
            - name: aliyun-slb-vpc-type
              resource: aliyun.slb
              filters:
                - type: vpc-type
                  vpcIds: ["111", "222"]
    """
    schema = type_schema(
        'vpc-type',
        **{'vpcIds': {'type': 'array', 'items': {'type': 'string'}}})

    def get_request(self, i):
        vpcId = i['VpcId']
        if vpcId in self.data['vpcIds']:
            return False
        return i


@Slb.filter_registry.register('bandwidth')
class BandwidthSlbFilter(AliyunSlbFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下的负载均衡实例是否达到最低带宽要求。
            - name: aliyun-slb-bandwidth
              resource: aliyun.slb
              filters:
                - type: bandwidth
                  value: 10
    """
    schema = type_schema(
        'bandwidth',
        **{'value': {'type': 'number'}})

    def get_request(self, i):
        request = DescribeLoadBalancerAttributeRequest()
        request.set_accept_format('json')
        request.set_LoadBalancerId(i['LoadBalancerId'])
        response = Session.client(self, service).do_action_with_exception(request)
        string = str(response, encoding="utf-8").replace("false", "False").replace("true", "True")
        data = eval(string)
        if self.data['value'] < data['Bandwidth']:
            return False
        data['F2CId'] = data['LoadBalancerId']
        return data


@Slb.filter_registry.register('acls')
class AclsSlbFilter(AliyunSlbFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 账号下SLB不允许任意来源公网访问，视为“合规”
            - name: aliyun-slb-acls
              resource: aliyun.slb
              filters:
                - type: acls
                  value: true
    """
    schema = type_schema(
        'acls',
        **{'value': {'type': 'boolean'}})

    def get_request(self, i):
        AddressType = i.get('AddressType', '')
        if self.data.get('value', ''):
            if AddressType == "Internet":
                return i
            else:
                return None
        else:
            if AddressType == "Intranet":
                return i
            else:
                return None
        return i
