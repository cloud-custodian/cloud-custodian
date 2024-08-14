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
from aliyunsdkr_kvstore.request.v20150101.DescribeInstancesRequest import DescribeInstancesRequest
from aliyunsdkr_kvstore.request.v20150101.DescribeSecurityIpsRequest import DescribeSecurityIpsRequest
from aliyunsdkr_kvstore.request.v20150101.DescribeSecurityGroupConfigurationRequest import DescribeSecurityGroupConfigurationRequest


from c7n.utils import type_schema
from c7n_aliyun.client import Session
from c7n_aliyun.filters.filter import AliyunRedisFilter
from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo

logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s', datefmt='%a, %d %b %Y %H:%M:%S')

service = 'redis'
regionId = os.getenv('ALIYUN_DEFAULT_REGION')

@resources.register('redis')
class Redis(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'redis'
        enum_spec = (None, 'Instances.KVStoreInstance', None)
        id = 'InstanceId'

    def get_request(self):
        return DescribeInstancesRequest()

@Redis.filter_registry.register('network-type')
class NetworkTypeRedisFilter(AliyunRedisFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下的Redis实例是否运行在VPC网络环境下
            - name: aliyun-redis-network-type
              resource: aliyun.redis
              filters:
                - type: network-type
                  value: VPC
    """
    # 实例的网络类型，取值：
    #
    # CLASSIC：经典网络
    # VPC：VPC网络
    schema = type_schema(
        'network-type',
        **{'value': {'type': 'string'}})

    def get_request(self, i):
        if self.data['value'] == i['NetworkType']:
            return False
        return i

@Redis.filter_registry.register('internet-access')
class InternetAccessMongoDBFilter(AliyunRedisFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 账号下Redis实例不允许任意来源公网访问，视为“合规”
            - name: aliyun-redis-internet-access
              resource: aliyun.redis
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