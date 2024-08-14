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

from aliyunsdkdds.request.v20151201.DescribeDBInstancesRequest import DescribeDBInstancesRequest
from aliyunsdkdds.request.v20151201.DescribeShardingNetworkAddressRequest import DescribeShardingNetworkAddressRequest

from c7n.utils import type_schema
from c7n_aliyun.filters.filter import AliyunRdsFilter
from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo
from c7n_aliyun.client import Session

logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s', datefmt='%a, %d %b %Y %H:%M:%S')

service = 'mongodb'
regionId = os.getenv('ALIYUN_DEFAULT_REGION')

@resources.register('mongodb')
class MongoDB(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'mongodb'
        enum_spec = (None, 'DBInstances.DBInstance', None)
        id = 'InstanceId'

    def get_request(self):
        return DescribeDBInstancesRequest()

@MongoDB.filter_registry.register('network-type')
class NetworkTypeMongoDBFilter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下的MongoDB实例是否运行在VPC网络环境下
            - name: aliyun-mongodb-network-type
              resource: aliyun.mongodb
              filters:
                - type: network-type
                  value: VPC
    """
    # 实例的网络类型，取值：
    #
    # Classic：经典网络
    # VPC：VPC网络
    schema = type_schema(
        'network-type',
        **{'value': {'type': 'string'}})

    def get_request(self, i):
        if self.data['value'] == i['NetworkType']:
            return False
        return i

@MongoDB.filter_registry.register('internet-access')
class InternetAccessMongoDBFilter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 账号下MongoDB实例不允许任意来源公网访问，视为“合规”
            - name: aliyun-mongodb-internet-access
              resource: aliyun.mongodb
              filters:
                - type: internet-access
                  value: true
    """
    schema = type_schema(
        'internet-access',
        **{'value': {'type': 'boolean'}})

    def get_request(self, i):

        request = DescribeShardingNetworkAddressRequest()
        request.set_accept_format('json')

        request.set_DBInstanceId(i.get('DBInstanceId', ''))
        response = Session.client(self, service).do_action_with_exception(request)
        string = str(response, encoding="utf-8").replace("false", "False").replace("true", "True")
        data = eval(string)
        CompatibleConnections = data.get('CompatibleConnections', {}).get('CompatibleConnection', [])
        NetworkAddresses = data.get('NetworkAddresses', {}).get('NetworkAddress', [])
        if self.data.get('value', '') == True:
            for c in CompatibleConnections:
                if c.get('NetworkType', '') == 'Public':
                    return i
            for n in NetworkAddresses:
                if n.get('NetworkType', '') == 'Public':
                    return i
        else:
            for c in CompatibleConnections:
                if c.get('NetworkType', '') != 'Public':
                    return i
            for n in NetworkAddresses:
                if n.get('NetworkType', '') != 'Public':
                    return i
        return None