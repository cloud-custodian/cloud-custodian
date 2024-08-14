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

import operator

import jmespath
from aliyunsdkcms.request.v20190101.DescribeMetricListRequest import DescribeMetricListRequest
from aliyunsdkecs.request.v20140526.DescribeInstancesRequest import DescribeInstancesRequest
from aliyunsdkecs.request.v20140526.StartInstanceRequest import StartInstanceRequest
from aliyunsdkecs.request.v20140526.StopInstanceRequest import StopInstanceRequest

from c7n.utils import type_schema
from c7n_aliyun.filters.filter import AliyunAgeFilter, AliyunEcsFilter, MetricsFilter
from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo


@resources.register('ecs')
class Ecs(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'ecs'
        enum_spec = (None, 'Instances.Instance', None)
        id = 'InstanceId'
        dimension = 'InstanceId'

    def get_request(self):
        request = DescribeInstancesRequest()
        return request

@Ecs.filter_registry.register('public-ip-address')
class PublicIpAddress(AliyunEcsFilter):

    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # ECS实例未直接绑定公网IP，视为“合规”。该规则仅适用于 IPv4 协议
            - name: aliyun-ecs-public-ipaddress
              resource: aliyun.ecs
              filters:
                - type: public-ip-address
    """
    public_ip_address = "PublicIpAddress.IpAddress"
    schema = type_schema('PublicIpAddress')

    def get_request(self, i):
        data = jmespath.search(self.public_ip_address, i)
        if len(data) == 0:
            return False
        return i

@Ecs.filter_registry.register('instance-age')
class EcsAgeFilter(AliyunAgeFilter):
    """Filters instances based on their age (in days)

    :Example:

    .. code-block:: yaml

        policies:
          - name: ecs-30-days-plus
            resource: aliyun.ecs
            filters:
              - type: instance-age
                op: ge
                minutes: 1
    """

    date_attribute = "LaunchTime"
    ebs_key_func = operator.itemgetter('AttachTime')

    schema = type_schema(
        'instance-age',
        op={'$ref': '#/definitions/filters_common/comparison_operators'},
        days={'type': 'number'},
        hours={'type': 'number'},
        minutes={'type': 'number'})

    def get_resource_date(self, i):
        return i['CreationTime']

@Ecs.filter_registry.register('metrics')
class EcsMetricsFilter(MetricsFilter):

    def get_request(self, r):
        request = DescribeMetricListRequest()
        request.set_accept_format('json')
        request.set_StartTime(self.start)
        dimensions = self.get_dimensions(r)
        request.set_Dimensions(dimensions)
        request.set_Period(self.period)
        request.set_Namespace(self.namespace)
        request.set_MetricName(self.metric)
        return request


@Ecs.filter_registry.register('instance-network-type')
class InstanceNetworkTypeEcsFilter(AliyunEcsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 账号下所有ECS实例已关联到VPC；若您配置阈值，则关联的VpcId需存在您列出的阈值中，视为“合规”
            - name: aliyun-ecs-instance-network-type
              resource: aliyun.ecs
              filters:
                - type: instance-network-type
                  value: vpc
    """
    # 实例的网络类型，取值：
    #
    # classic：经典网络
    # vpc：专有网络VPC
    schema = type_schema(
        'instance-network-type',
        **{'value': {'type': 'string'}})

    def get_request(self, i):
        if self.data['value'] == i['InstanceNetworkType']:
            return False
        return i

@Ecs.filter_registry.register('vpc-type')
class VpcTypeEcsFilter(AliyunEcsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下的Ecs实例指定属于哪些VPC, 属于则合规，不属于则"不合规"。
            - name: aliyun-ecs-vpc-type
              resource: aliyun.ecs
              filters:
                - type: vpc-type
                  vpcIds: ["111", "222"]
    """
    schema = type_schema(
        'vpc-type',
        **{'vpcIds': {'type': 'array', 'items': {'type': 'string'}}})

    def get_request(self, i):
        vpcId = i['VpcAttributes']['VpcId']
        if vpcId in self.data['vpcIds']:
            return False
        return i

@Ecs.filter_registry.register('stopped')
class AliyunEcsFilter(AliyunEcsFilter):
    """Filters

       :Example:

       .. code-block:: yaml

           policies:
             - name: aliyun-ecs
               resource: aliyun.ecs
               filters:
                 - type: stopped
    """
    # 实例状态。取值范围：
    #
    # Pending：创建中
    # Running：运行中
    # Starting：启动中
    # Stopping：停止中
    # Stopped：已停止
    schema = type_schema('Stopped')

    def get_request(self, i):
        status = i.get('Status', '')
        if 'Stopped' != status:
            return False
        return i

@Ecs.filter_registry.register('instance-age')
class EcsAgeFilter(AliyunAgeFilter):
    """Filters instances based on their age (in days)

    :Example:

    .. code-block:: yaml

        policies:
          - name: ecs-30-days-plus
            resource: aliyun.ecs
            filters:
              - type: instance-age
                op: ge
                minutes: 1
    """

    date_attribute = "LaunchTime"
    ebs_key_func = operator.itemgetter('AttachTime')

    schema = type_schema(
        'instance-age',
        op={'$ref': '#/definitions/filters_common/comparison_operators'},
        days={'type': 'number'},
        hours={'type': 'number'},
        minutes={'type': 'number'})

    def get_resource_date(self, i):
        return i['CreationTime']