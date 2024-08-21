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

from aliyunsdkcdn.request.v20180510.DescribeUserDomainsRequest import DescribeUserDomainsRequest

from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo
from c7n_aliyun.filters.filter import AliyunCdnFilter
from c7n.utils import type_schema

service = 'cdn'


@resources.register('cdn')
class Cdn(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'cdn'
        enum_spec = (None, 'Domains.PageData', None)
        id = 'Cname'

    def get_request(self):
        request = DescribeUserDomainsRequest()
        return request


@Cdn.filter_registry.register('ssl-protocol')
class SslProtocolCdnFilter(AliyunCdnFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测CDN域名是否开启HTTPS监听，若开启视为“合规”。
            - name: aliyun-cdn-ssl-protocol
              resource: aliyun.cdn
              filters:
                - type: ssl-protocol
                  value: "off"
    """
    schema = type_schema(
        'ssl-protocol',
        **{'value': {'type': 'string'}})

    def get_request(self, i):
        if self.data['value'] != i['SslProtocol']:
            return False
        return i
