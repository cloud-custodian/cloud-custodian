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
import logging
import os

import jmespath
from aliyunsdkcms.request.v20190101.DescribeMetricListRequest import DescribeMetricListRequest
from aliyunsdkrds.request.v20140815.DescribeAvailableZonesRequest import DescribeAvailableZonesRequest
from aliyunsdkrds.request.v20140815.DescribeDBInstanceAttributeRequest import DescribeDBInstanceAttributeRequest
from aliyunsdkrds.request.v20140815.DescribeDBInstancesRequest import DescribeDBInstancesRequest
from aliyunsdkrds.request.v20140815.DescribeSecurityGroupConfigurationRequest import \
    DescribeSecurityGroupConfigurationRequest
from aliyunsdkrds.request.v20140815.DescribeDBInstanceIPArrayListRequest import DescribeDBInstanceIPArrayListRequest

from c7n.utils import type_schema
from c7n_aliyun.client import Session
from c7n_aliyun.filters.filter import AliyunRdsFilter, MetricsFilter
from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo

logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')

service = 'rds'
regionId = os.getenv('ALIYUN_DEFAULT_REGION')


@resources.register('rds')
class Rds(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'rds'
        enum_spec = (None, 'Items.DBInstance', None)
        id = 'DBInstanceId'

    def get_request(self):
        request = DescribeDBInstancesRequest()
        return request


@Rds.filter_registry.register('available-zones')
class AvailableZonesRdsFilter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 账号下RDS实例支持多可用区，视为“合规”。
            - name: aliyun-rds-availablezones
              resource: aliyun.rds
              filters:
                - type: available-zones
                  value: false
    """
    schema = type_schema(
        'available-zones',
        **{'value': {'type': 'boolean'}})
    filter = None

    def get_request(self, i):
        request = DescribeAvailableZonesRequest()
        request.set_accept_format('json')
        # 数据库类型。取值：
        # MySQL
        # SQLServer
        # PostgreSQL
        # PPAS
        # MariaDB
        request.set_Engine(i['Engine'])

        response = Session.client(self, service).do_action_with_exception(request)

        string = str(response, encoding="utf-8").replace("false", "False").replace("true", "True")
        data = eval(string)
        if self.data['value'] == True:
            flag = len(data['AvailableZones']) > 0
        else:
            flag = len(data['AvailableZones']) < 0
        if flag != self.data['value']:
            return False
        return i


@Rds.filter_registry.register('security-ip-mode')
class AliyunRdsFilter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            #检测您账号下RDS数据库实例是否启用安全白名单功能，已开通视为“合规”
            - name: aliyun-rds-security-ip-mode
              resource: aliyun.rds
              filters:
                - type: security-ip-mode
                  value: safety
    """
    # 白名单模式。取值：
    #
    # normal：通用模式
    # safety：高安全模式
    schema = type_schema(
        'security-ip-mode',
        **{'value': {'type': 'string'}})

    def get_request(self, i):
        request = DescribeDBInstanceAttributeRequest()
        request.set_accept_format('json')

        request.set_DBInstanceId(i['DBInstanceId'])
        response = Session.client(self, service).do_action_with_exception(request)
        string = str(response, encoding="utf-8").replace("false", "False").replace("true", "True")
        data = eval(string)
        DBInstanceAttributes = data['Items']['DBInstanceAttribute']
        for obj in DBInstanceAttributes:
            if obj['SecurityIPMode'] == self.data['value']:
                return False
        i['DBInstanceAttributes'] = DBInstanceAttributes
        return i


@Rds.filter_registry.register('high-availability')
class HighAvailabilityRdsFilter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 账号下RDS实例具备高可用能力，视为“合规”，否则属于“不合规”。
            - name: aliyun-rds-high-availability
              resource: aliyun.rds
              filters:
                - type: high-availability
    """
    # 实例系列，取值：
    #
    # Basic：基础版
    # HighAvailability：高可用版
    # AlwaysOn：集群版
    # Finance：三节点企业版
    schema = type_schema('Basic')
    filter = 'Category'

    def get_request(self, i):
        request = DescribeDBInstanceAttributeRequest()
        request.set_accept_format('json')

        request.set_DBInstanceId(i['DBInstanceId'])
        response = Session.client(self, service).do_action_with_exception(request)
        string = str(response, encoding="utf-8").replace("false", "False").replace("true", "True")
        data = eval(string)
        DBInstanceAttributes = data['Items']['DBInstanceAttribute']
        for obj in DBInstanceAttributes:
            if obj[self.filter] == self.data['type']:
                return False
        i['DBInstanceAttributes'] = DBInstanceAttributes
        return i


@Rds.filter_registry.register('metrics')
class RdsMetricsFilter(MetricsFilter):
    """
          1 policies:
          2   - name: aliyun-rds-metrics
          3     resource: aliyun.rds
          4     filters:
          6       - type: metrics
          7         name: IOPSUsage
          9         startTime: '2020-11-02T08:00Z'
         10         endTime: '2020-11-08T08:00Z'
         11         statistics: Average
         12         value: 30000
         13         op: less-than
    """

    # IOPS使用率:IOPSUsage
    # 连接数使用率: ConnectionUsage
    # 内存使用率: MemoryUsage
    # CPU使用率: CpuUsage
    def get_request(self, rds):
        request = DescribeMetricListRequest()
        request.set_accept_format('json')
        dimensions = self.get_dimensions(rds)
        request.set_Dimensions(dimensions)
        request.set_StartTime(self.start)
        request.set_Period(self.period)
        request.set_Namespace(self.namespace)
        request.set_MetricName(self.metric)
        return request


@Rds.filter_registry.register('connection-mode')
class ConnectionModeRds2Filter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下的RDS实例是否启用数据库代理状态链接形式，Safe视为“合规”，Standard属于“不合规”。
            - name: aliyun-rds-connection-mode
              resource: aliyun.rds
              filters:
                - type: connection-mode
                  value: Safe
    """
    # 实例的访问模式，取值：
    #
    # Standard：标准访问模式
    # Safe：数据库代理模式
    # 默认返回所有访问模式下的实例
    schema = type_schema(
        'connection-mode',
        **{'value': {'type': 'string'}})

    def get_request(self, i):
        if self.data['value'] == i['ConnectionMode']:
            return False
        return i


@Rds.filter_registry.register('vpc-type')
class VpcTypeRdsFilter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下的Rds实例指定属于哪些VPC, 属于则合规，不属于则"不合规"。
            - name: aliyun-rds-vpc-type
              resource: aliyun.rds
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


@Rds.filter_registry.register('instance-network-type')
class InstanceNetworkTypeRdsFilter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下的Redis实例是否运行在VPC网络环境下。
            - name: aliyun-rds-instance-network-type
              resource: aliyun.rds
              filters:
                - type: instance-network-type
                  value: VPC
    """
    # 实例的网络类型，取值：
    #
    # Classic：经典网络
    # VPC：VPC网络
    schema = type_schema(
        'instance-network-type',
        **{'value': {'type': 'string'}})

    def get_request(self, i):
        if self.data['value'] == i['InstanceNetworkType']:
            return False
        return i


@Rds.filter_registry.register('internet-access')
class InternetAccessRdsFilter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下RDS实例不允许任意来源公网访问，视为“合规”
            - name: aliyun-rds-internet-access
              resource: aliyun.rds
              filters:
                - type: internet-access
                  value: true
    """
    schema = type_schema(
        'internet-access',
        **{'value': {'type': 'boolean'}})

    def get_request(self, i):
        DBInstanceNetType = i.get('DBInstanceNetType', '')
        if self.data.get('value', ''):
            if DBInstanceNetType == "Internet":
                return i
            else:
                return None
        else:
            if DBInstanceNetType == "Intranet":
                return i
            else:
                return None
        return i

    def is_internal_ip(self, ip):
        ip = self.ip_into_int(ip)
        net_a = self.ip_into_int('10.255.255.255') >> 24
        net_b = self.ip_into_int('172.31.255.255') >> 20
        net_c = self.ip_into_int('192.168.255.255') >> 16
        return ip >> 24 == net_a or ip >> 20 == net_b or ip >> 16 == net_c

    def ip_into_int(self, ip):
        # 先把 192.168.31.46 用map分割'.'成数组，然后用reduuce+lambda转成10进制的 3232243502
        # (((((192 * 256) + 168) * 256) + 31) * 256) + 46
        return self.reduce(lambda x, y: (x << 8) + y, map(int, ip.split('.')))
