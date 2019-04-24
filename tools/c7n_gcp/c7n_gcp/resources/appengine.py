# Copyright 2019 Capital One Services, LLC
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

import re

from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo
from c7n.utils import local_session


@resources.register('appengine-app')
class AppEngineApp(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'appengine'
        version = 'v1'
        component = 'apps'
        enum_spec = ('get', '[@]', None)
        scope = None
        id = 'id'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'appsId': re.compile('apps/(.*)').match(
                    resource_info['resourceName']).group(1)})

    def get_resource_query(self):
        return {'appsId': local_session(self.session_factory).get_default_project()}
