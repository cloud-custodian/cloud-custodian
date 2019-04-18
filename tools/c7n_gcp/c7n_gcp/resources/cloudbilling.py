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
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('cloudbilling-account')
class CloudBillingAccount(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudbilling'
        version = 'v1'
        component = 'billingAccounts'
        enum_spec = ('list', 'billingAccounts[]', None)
        scope = None
        id = 'name'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'name': resource_info['name']})
