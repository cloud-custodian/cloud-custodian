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
from aliyunsdkecs.request.v20140526.DescribeSecurityGroupAttributeRequest import DescribeSecurityGroupAttributeRequest
from aliyunsdkecs.request.v20140526.DescribeSecurityGroupsRequest import DescribeSecurityGroupsRequest
from aliyunsdkecs.request.v20140526.DescribeVpcsRequest import DescribeVpcsRequest

from c7n.utils import type_schema
from c7n_aliyun.client import Session
from c7n_aliyun.filters.filter import AliyunSgFilter
from c7n_aliyun.filters.filter import AliyunVpcFilter
from c7n_aliyun.filters.filter import SGPermission
from c7n_aliyun.filters.filter import SGPermissionSchema
from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo
from c7n_aliyun.resources.ecs import Ecs
from c7n_aliyun.resources.rds import Rds


@resources.register('vpc')
class Vpc(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'vpc'
        enum_spec = (None, 'Vpcs.Vpc', None)
        id = 'VpcId'

    def get_request(self):
        request = DescribeVpcsRequest()
        return request

@Vpc.filter_registry.register('unused')
class AliyunVpcFilter(AliyunVpcFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            - name: aliyun-avalible-vpc
              resource: aliyun.vpc
              filters:
                - tyvaluepe: unused
    """
    # Associating：绑定中。
    # Unassociating：解绑中。
    # InUse：已分配。
    # Available：可用。
    schema = type_schema('Available')

    def get_request(self, i):
        VpcId = i['VpcId']
        #vpc 查询vpc下是否有ECS资源
        ecs_request = Ecs.get_request(self)
        ecs_request.set_accept_format('json')
        ecs_response_str = Session.client(self, service='ecs').do_action(ecs_request)
        ecs_response_detail = json.loads(ecs_response_str)
        if ecs_response_detail['Instances']['Instance']:
            for ecs in ecs_response_detail['Instances']['Instance']:
                if VpcId == ecs['VpcAttributes']['VpcId']:
                    return None
        # vpc 查询vpc下是否有RDS资源
        rds_request = Rds.get_request(self)
        if not rds_request:
            return i
        rds_request.set_accept_format('json')
        rds_response_str = Session.client(self, service='ecs').do_action(rds_request)
        rds_response_detail = json.loads(rds_response_str)
        if rds_response_detail['Items']['DBInstance']:
            for rds in rds_response_detail['Items']['DBInstance']:
                if VpcId == rds['VpcId']:
                    return None
        return i

# 删除vpc 需要先删除底下所有资源（子网等）
# @Vpc.action_registry.register('delete')
# class Delete(MethodAction):
#
#     schema = type_schema('delete')
#     method_spec = {'op': 'delete'}
#
#     def get_request(self, vpc):
#         request = DeleteVpcRequest()
#         request.set_InstanceId(vpc['VpcId'])
#         request.set_accept_format('json')
#         return request


@resources.register('security-group')
class SecurityGroup(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'security-group'
        enum_spec = (None, 'SecurityGroups.SecurityGroup', None)
        id = 'SecurityGroupId'

    def get_request(self):
        request = DescribeSecurityGroupsRequest()
        return request

@SecurityGroup.filter_registry.register('source-cidr-ip')
class IPPermission(AliyunSgFilter):

    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 账号下ECS安全组配置不为“0.0.0.0/0”，视为“合规”。
            - name: aliyun-sg-sourcecidrip
              resource: aliyun.security-group
              filters:
                - type: source-cidr-ip
                  value: "0.0.0.0/0"
    """

    ip_permissions_key = "Permissions.Permission"
    schema = type_schema(
        'source-cidr-ip',
        **{'value': {'type': 'string'}})

    def get_request(self, sg):
        service = 'security-group'
        request = DescribeSecurityGroupAttributeRequest()
        request.set_SecurityGroupId(sg["SecurityGroupId"])
        request.set_Direction("ingress")
        request.set_accept_format('json')
        response = Session.client(self, service).do_action_with_exception(request)
        string = str(response, encoding="utf-8").replace("false", "False").replace("true", "True")
        data = eval(string)
        for cidr in jmespath.search(self.ip_permissions_key, data):
            if cidr['SourceCidrIp'] == self.data['value']:
                sg['cidr'] = cidr
                return sg
        return False

@SecurityGroup.filter_registry.register('source-ports')
class IPPermission(AliyunSgFilter):

    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 账号下ECS安全组配置允许所有端口访问视为不合规，否则为合规
            - name: aliyun-sg-ports
              resource: aliyun.security-group
              filters:
                - type: source-ports
                  SourceCidrIp: "0.0.0.0/0"
                  PortRange: -1/-1
    """

    ip_permissions_key = "Permissions.Permission"
    schema = type_schema(
        'source-ports',
        **{'SourceCidrIp': {'type': 'string'},
        'PortRange': {'type': 'string'}}
    )

    def get_request(self, sg):
        service = 'security-group'
        request = DescribeSecurityGroupAttributeRequest();
        request.set_SecurityGroupId(sg["SecurityGroupId"])
        request.set_Direction("ingress")
        request.set_accept_format('json')
        response = Session.client(self, service).do_action_with_exception(request)
        string = str(response, encoding="utf-8").replace("false", "False").replace("true", "True")
        data = eval(string)
        for ports in jmespath.search(self.ip_permissions_key, data):
            if ports['SourceCidrIp'] == self.data['SourceCidrIp']:
                if ports['PortRange'] == self.data['PortRange']:
                    return sg
                values = self.data['PortRange'].split('/')
                if values[0].replace("”", "") == "-1":
                    fromPort = 0
                    toPort = 65535
                else:
                    fromPort = int(values[0].replace("”", ""))
                    toPort = int(values[1].replace("”", ""))
                if '/' in ports['PortRange']:
                    strs = ports['PortRange'].split('/')
                    port1 = int(strs[0])
                    port2 = int(strs[1])
                    if (fromPort >= port1 and fromPort <= port2) \
                            or (toPort >= port1 and toPort <= port2):
                        return sg
        return False

@SecurityGroup.filter_registry.register('ingress')
class IPPermission(SGPermission):

    ip_permissions_key = "Permissions.Permission"
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {'type': {'enum': ['ingress']}},
        'required': ['type']}
    schema['properties'].update(SGPermissionSchema)

    def process_self_cidrs(self, perm):
        return self.process_cidrs(perm, "SourceCidrIp", "Ipv6SourceCidrIp")

    def securityGroupAttributeRequst(self, sg):
        requst = DescribeSecurityGroupAttributeRequest();
        requst.set_SecurityGroupId(sg["SecurityGroupId"])
        requst.set_Direction("ingress")
        requst.set_accept_format('json')
        return requst


@SecurityGroup.filter_registry.register('egress')
class IPPermission(SGPermission):
    ip_permissions_key = "Permissions.Permission"
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {'type': {'enum': ['egress']}},
        'required': ['type']}
    schema['properties'].update(SGPermissionSchema)

    def securityGroupAttributeRequst(self, sg):
        requst = DescribeSecurityGroupAttributeRequest();
        requst.set_SecurityGroupId(sg["SecurityGroupId"])
        requst.set_Direction("egress")
        requst.set_accept_format('json')
        return requst

    def process_self_cidrs(self, perm):
        return self.process_cidrs(perm, "DestCidrIp", "Ipv6DestCidrIp")
