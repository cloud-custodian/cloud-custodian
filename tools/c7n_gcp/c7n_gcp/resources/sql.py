# Copyright 2018 Capital One Services, LLC
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

from c7n.utils import type_schema
from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo


@resources.register('sql-instance')
class SqlInstance(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sqladmin'
        version = 'v1beta4'
        component = 'instances'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        id = 'name'

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'instance': resource_info['database_id'].rsplit(':', 1)[-1]})


class SqlInstanceAction(MethodAction):

    def get_resource_params(self, model, resource):
        project, instance = self.path_param_re.match(
            resource['selfLink']).groups()
        return {'project': project, 'instance': instance}


@SqlInstance.action_registry.register('delete')
class SqlInstanceDelete(SqlInstanceAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    path_param_re = re.compile(
        '.*?/projects/(.*?)/instances/(.*)')


@SqlInstance.action_registry.register('stop')
class SqlInstanceStop(MethodAction):

    schema = type_schema('stop')
    method_spec = {'op': 'patch'}
    path_param_re = re.compile('.*?/projects/(.*?)/instances/(.*)')

    def get_resource_params(self, model, resource):
        project, instance = self.path_param_re.match(
            resource['selfLink']).groups()
        return {'project': project,
                'instance': instance,
                'body': {'settings': {'activationPolicy': 'NEVER'}}}


@resources.register('sql-database')
class SqlDatabase(ChildResourceManager):

    def _get_parent_resource_info(self, child_instance):
        project = child_instance['project']
        return {
            'project_id': child_instance['project'],
            'database_id': '{}:{}'.format(project, child_instance['instance'])
        }

    class resource_type(ChildTypeInfo):
        service = 'sqladmin'
        version = 'v1beta4'
        component = 'databases'
        enum_spec = ('list', 'items[]', None)
        id = 'name'
        parent_spec = {
            'resource': 'sql-instance',
            'child_enum_params': [
                ('name', 'instance')
            ]
        }

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project'],
                        'database': resource_info['name'],
                        'instance': resource_info['instance']}
            )


@resources.register('sql-user')
class SqlUser(ChildResourceManager):

    class resource_type(ChildTypeInfo):
        service = 'sqladmin'
        version = 'v1beta4'
        component = 'users'
        enum_spec = ('list', 'items[]', None)
        id = 'name'
        parent_spec = {
            'resource': 'sql-instance',
            'child_enum_params': [
                ('name', 'instance')
            ]
        }


class SqlInstanceChildWithSelfLink(ChildResourceManager):
    """A ChildResourceManager for resources that reference SqlInstance in selfLink.
    """

    def _get_parent_resource_info(self, child_instance):
        """
        :param child_instance: a dictionary to get parent parameters from
        :return: project_id and database_id extracted from child_instance
        """
        return {'project_id': re.match('.*?/projects/(.*?)/instances/.*',
                                    child_instance['selfLink']).group(1),
                'database_id': child_instance['instance']}

    @staticmethod
    def _get_base_query_parameters(resource_info):
        """
        :param resource_info: a dictionary to get query parameters from
        :return: project and instance extracted from resource_info
        """
        return {'project': resource_info['project_id'],
                'instance': resource_info['database_id'].split(':')[1]}


@resources.register('sql-backup-run')
class SqlBackupRun(SqlInstanceChildWithSelfLink):

    class resource_type(ChildTypeInfo):
        service = 'sqladmin'
        version = 'v1beta4'
        component = 'backupRuns'
        enum_spec = ('list', 'items[]', None)
        id = 'id'
        parent_spec = {
            'resource': 'sql-instance',
            'child_enum_params': [
                ('name', 'instance')
            ]
        }

        @staticmethod
        def get(client, resource_info):
            parameters = SqlInstanceChildWithSelfLink._get_base_query_parameters(resource_info)
            parameters['id'] = resource_info['backup_run_id']
            return client.execute_command('get', parameters)


@resources.register('sql-ssl-cert')
class SqlSslCert(SqlInstanceChildWithSelfLink):

    class resource_type(ChildTypeInfo):
        service = 'sqladmin'
        version = 'v1beta4'
        component = 'sslCerts'
        enum_spec = ('list', 'items[]', None)
        id = 'sha1Fingerprint'
        parent_spec = {
            'resource': 'sql-instance',
            'child_enum_params': [
                ('name', 'instance')
            ]
        }

        @staticmethod
        def get(client, resource_info):
            parameters = SqlInstanceChildWithSelfLink._get_base_query_parameters(resource_info)
            parameters['sha1Fingerprint'] = resource_info['sha_1_fingerprint']
            return client.execute_command('get', parameters)
