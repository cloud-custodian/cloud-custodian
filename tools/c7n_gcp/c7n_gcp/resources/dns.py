# Copyright 2018-2019 Capital One Services, LLC
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


@resources.register('dns-managed-zone')
class DnsManagedZone(QueryResourceManager):
    """GCP resource: https://cloud.google.com/dns/docs/reference/v1beta2/managedZones
    """
    class resource_type(TypeInfo):
        service = 'dns'
        version = 'v1beta2'
        component = 'managedZones'
        enum_spec = ('list', 'managedZones[]', None)
        scope = 'project'
        id = 'id'
        name = 'name'
        default_report_fields = ['id', 'name', 'dnsName', 'creationTime', 'visibility']

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'project': resource_info['project_id'],
                        'managedZone': resource_info['zone_name']})


@resources.register('dns-policy')
class DnsPolicy(QueryResourceManager):
    """GCP resource: https://cloud.google.com/dns/docs/reference/v1beta2/policies
    """
    class resource_type(TypeInfo):
        service = 'dns'
        version = 'v1beta2'
        component = 'policies'
        enum_spec = ('list', 'policies[]', None)
        scope = 'project'
        id = 'id'
        name = 'name'
        default_report_fields = ['id', 'name', 'description', 'enableLogging']

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'project': resource_info['project_id'],
                        'policy': resource_info['policy_name']})
