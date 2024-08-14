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
from aliyunsdkpolardb.request.v20170801.DescribeDBClustersRequest import DescribeDBClustersRequest
from aliyunsdkpolardb.request.v20170801.DescribeDBClusterAccessWhitelistRequest import DescribeDBClusterAccessWhitelistRequest

from c7n.utils import type_schema
from c7n_aliyun.filters.filter import AliyunRdsFilter
from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo
from c7n_aliyun.client import Session

logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s', datefmt='%a, %d %b %Y %H:%M:%S')

service = 'polardb'
regionId = os.getenv('ALIYUN_DEFAULT_REGION')

@resources.register('polardb')
class PolarDB(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'polardb'
        enum_spec = (None, 'Items.DBCluster', None)
        id = 'DBClusterId'

    def get_request(self):
        return DescribeDBClustersRequest()

@PolarDB.filter_registry.register('vpc-type')
class VpcTypePolarDBFilter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下的Polardb实例指定属于哪些VPC, 属于则合规，不属于则"不合规"。
            - name: aliyun-polardb-vpc-type
              resource: aliyun.polardb
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

@PolarDB.filter_registry.register('dbcluster-network-type')
class DBClusterNetworkTypePolarDBFilter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下的polardb实例是否运行在vpc网络环境下
            - name: aliyun-polardb-dbcluster-network-type
              resource: aliyun.polardb
              filters:
                - type: dbcluster-network-type
                  value: VPC
    """
    # 实例的网络类型，取值：
    #
    # CLASSIC：经典网络
    # VPC：VPC网络
    schema = type_schema(
        'dbcluster-network-type',
        **{'value': {'type': 'string'}})

    def get_request(self, i):
        if self.data['value'] == i['DBClusterNetworkType']:
            return False
        return i

@PolarDB.filter_registry.register('internet-access')
class InternetAccessPolarDBFilter(AliyunRdsFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 账号下Polar实例不允许任意来源公网访问，视为“合规”
            - name: aliyun-polardb-internet-access
              resource: aliyun.polardb
              filters:
                - type: internet-access
                  value: true
    """
    schema = type_schema(
        'internet-access',
        **{'value': {'type': 'boolean'}})

    def get_request(self, i):
        request = DescribeDBClusterAccessWhitelistRequest()
        request.set_accept_format('json')
        request.set_DBClusterId(i.get('DBClusterId', ''))
        response = Session.client(self, service).do_action_with_exception(request)
        string = str(response, encoding="utf-8").replace("false", "False").replace("true", "True")
        data = eval(string)
        DBClusterSecurityGroups = jmespath.search('DBClusterSecurityGroups.DBClusterSecurityGroup', data)
        DBClusterIPArray = jmespath.search('Items.DBClusterIPArray', data)
        if self.data['value']:
            if len(DBClusterSecurityGroups) == 0 and len(DBClusterIPArray) == 0:
                return False
        else:
            return False
        i['DBClusterSecurityGroups'] = DBClusterSecurityGroups
        i['DBClusterIPArray'] = DBClusterIPArray
        return i