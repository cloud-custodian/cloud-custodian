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
                'get', {'appsId': AppEngineApp.extract_app_id(resource_info['resourceName'])})

    def get_resource_query(self):
        if 'query' in self.data:
            return {'appsId': AppEngineApp.extract_app_id(self.data.get('query')[0]['app-name'])}

    @staticmethod
    def extract_app_id(app_name):
        return re.compile('apps/(.*)').match(app_name).group(1)
