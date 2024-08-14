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
import jmespath
from aliyunsdkram.request.v20150501.ListUsersRequest import ListUsersRequest
from aliyunsdkram.request.v20150501.GetUserMFAInfoRequest import GetUserMFAInfoRequest
from aliyunsdkram.request.v20150501.GetLoginProfileRequest import GetLoginProfileRequest

from c7n.utils import type_schema
from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo
from c7n_aliyun.filters.filter import AliyunRamFilter
from c7n_aliyun.client import Session

service = 'ram'
@resources.register('ram')
class Ram(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'ram'
        enum_spec = (None, 'Users.User', None)
        id = 'UserId'

    def get_request(self):
        request = ListUsersRequest()
        return request

@Ram.filter_registry.register('mfa')
class MFA(AliyunRamFilter):

    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测RAM用户是否开通MFA二次验证登录
            - name: aliyun-ram-mfa
              resource: aliyun.ram
              filters:
                - type: mfa
                  value: false
    """
    mfa_bind_required = 'LoginProfile.MFABindRequired'
    schema = type_schema(
        'mfa',
        **{'value': {'type': 'boolean'}})

    def get_request(self, i):
        try:
            request = GetLoginProfileRequest()
            request.set_accept_format('json')
            request.set_UserName(i['UserName'])
            response = Session.client(self, service).do_action_with_exception(request)
            string = str(response, encoding="utf-8").replace("false", "False").replace("true", "True")
            data = jmespath.search(self.mfa_bind_required, eval(string))
            if data != self.data['value']:
                return False
            i['MFABindRequired'] = jmespath.search('LoginProfile', eval(string))
        except Exception as err:
            pass
        return i
