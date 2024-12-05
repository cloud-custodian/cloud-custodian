# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import re

from c7n.utils import type_schema, jmespath_search
from c7n.filters.offhours import OffHour, OnHour
from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import (
    QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo
)
from datetime import datetime
from dateutil.parser import parse


@resources.register('sql-instance')
class SqlInstance(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sqladmin'
        version = 'v1beta4'
        component = 'instances'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        labels = True
        labels_op = 'patch'
        name = id = 'name'
        default_report_fields = [
            "name", "state", "databaseVersion", "settings.tier", "settings.dataDiskSizeGb"]
        asset_type = "sqladmin.googleapis.com/Instance"
        scc_type = "google.cloud.sql.Instance"
        metric_key = 'resource.labels.database_id'
        perm_service = 'cloudsql'
        urn_component = "instance"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'instance': resource_info['database_id'].rsplit(':', 1)[-1]})

        @staticmethod
        def get_metric_resource_name(resource):
            return "{}:{}".format(resource["project"], resource["name"])

        @staticmethod
        def get_label_params(resource, all_labels):
            path_param_re = re.compile('.*?/projects/(.*?)/instances/(.*)')
            project, instance = path_param_re.match(
                resource['selfLink']).groups()
            return {
                'project': project, 'instance': instance,
                'body': {
                    'settings': {
                        'userLabels': all_labels
                    }
                }
            }

    def augment(self, resources):
        for r in resources:
            if 'userLabels' in r['settings']:
                r['labels'] = r['settings']['userLabels']
        return resources


SqlInstance.filter_registry.register('offhour', OffHour)
SqlInstance.filter_registry.register('onhour', OnHour)


class SqlInstanceAction(MethodAction):

    def get_resource_params(self, model, resource):
        project, instance = self.path_param_re.match(
            resource['selfLink']).groups()
        return {'project': project, 'instance': instance}


@SqlInstance.action_registry.register('delete')
class SqlInstanceDelete(SqlInstanceAction):

    schema = type_schema('delete', force={'type': 'boolean'})
    method_spec = {'op': 'delete'}
    path_param_re = re.compile(
        '.*?/projects/(.*?)/instances/(.*)')

    def process(self, resources):
        if self.data.get('force'):
            self.disable_protection(resources)
        super().process(resources)

    def disable_protection(self, resources):
        deletion_protected = [
            r for r in resources if r['settings'].get('deletionProtectionEnabled')]
        disable_protection = SqlInstanceEnableDeletion({}, self.manager)
        disable_protection.process(deletion_protected)


@SqlInstance.action_registry.register('stop')
class SqlInstanceStop(MethodAction):

    schema = type_schema('stop')
    method_spec = {'op': 'patch'}
    path_param_re = re.compile('.*?/projects/(.*?)/instances/(.*)')
    method_perm = 'update'

    def get_resource_params(self, model, resource):
        project, instance = self.path_param_re.match(
            resource['selfLink']).groups()
        return {'project': project,
                'instance': instance,
                'body': {'settings': {'activationPolicy': 'NEVER'}}}


@SqlInstance.action_registry.register('start')
class SqlInstanceStart(MethodAction):

    schema = type_schema('start')
    method_spec = {'op': 'patch'}
    path_param_re = re.compile('.*?/projects/(.*?)/instances/(.*)')
    method_perm = 'update'

    def get_resource_params(self, model, resource):
        project, instance = self.path_param_re.match(
            resource['selfLink']).groups()
        return {'project': project,
                'instance': instance,
                'body': {'settings': {'activationPolicy': 'ALWAYS'}}}


@SqlInstance.action_registry.register('set-deletion-protection')
class SqlInstanceEnableDeletion(MethodAction):

    schema = type_schema(
        'set-deletion-protection',
        value={'type': 'boolean'})
    method_spec = {'op': 'patch'}
    path_param_re = re.compile('.*?/projects/(.*?)/instances/(.*)')
    method_perm = 'update'

    def get_resource_params(self, model, resource):
        project, instance = self.path_param_re.match(
            resource['selfLink']).groups()
        return {
            'project': project,
            'instance': instance,
            'body': {
                'settings': {
                    'deletionProtectionEnabled': str(self.data.get('value', True)).lower()
                }
            }
        }


@SqlInstance.action_registry.register('set-high-availability')
class SqlInstanceHighAvailability(MethodAction):

    schema = type_schema(
        'set-high-availability',
        value={'type': 'boolean', 'required': True})
    method_spec = {'op': 'patch'}
    path_param_re = re.compile('.*?/projects/(.*?)/instances/(.*)')
    method_perm = 'update'

    def get_resource_params(self, model, resource):
        if self.data['value'] is False:
            availabilityType = 'ZONAL'
        else:
            availabilityType = 'REGIONAL'

        project, instance = self.path_param_re.match(
            resource['selfLink']).groups()
        return {
            'project': project,
            'instance': instance,
            'body': {
                'settings': {
                    'availabilityType': availabilityType
                }
            }
        }


class SQLInstanceChildTypeInfo(ChildTypeInfo):
    service = 'sqladmin'
    version = 'v1beta4'
    parent_spec = {
        'resource': 'sql-instance',
        'child_enum_params': [
            ('name', 'instance')
        ]
    }
    perm_service = 'cloudsql'

    @classmethod
    def _get_location(cls, resource):
        return super()._get_location(cls.get_parent(resource))

    @classmethod
    def _get_urn_id(cls, resource):
        return f"{resource['instance']}/{resource[cls.id]}"


@resources.register('sql-user')
class SqlUser(ChildResourceManager):

    class resource_type(SQLInstanceChildTypeInfo):
        component = 'users'
        enum_spec = ('list', 'items[]', None)
        name = id = 'name'
        default_report_fields = ["name", "project", "instance"]
        urn_component = "user"


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


@resources.register('sql-backup-run')
class SqlBackupRun(SqlInstanceChildWithSelfLink):
    """GCP Resource
    https://cloud.google.com/sql/docs/mysql/admin-api/rest/v1beta4/backupRuns
    """
    class resource_type(SQLInstanceChildTypeInfo):
        component = 'backupRuns'
        enum_spec = ('list', 'items[]', None)
        get_requires_event = True
        name = id = 'id'
        default_report_fields = [
            name, "status", "instance", "location", "enqueuedTime", "startTime", "endTime"]
        urn_component = "backup-run"

        @staticmethod
        def get(client, event):
            project = jmespath_search('protoPayload.response.targetProject', event)
            instance = jmespath_search('protoPayload.response.targetId', event)
            insert_time = jmespath_search('protoPayload.response.insertTime', event)
            parameters = {'project': project,
                          'instance': instance,
                          'id': SqlBackupRun.resource_type._from_insert_time_to_id(insert_time)}
            return client.execute_command('get', parameters)

        @staticmethod
        def _from_insert_time_to_id(insert_time):
            """
            Backup Run id is not available in a log record directly.
            Fortunately, as it is an integer timestamp representation,
            it can be retrieved by converting raw insert_time value.

            :param insert_time: a UTC ISO formatted date time string
            :return: an integer number of microseconds since unix epoch
            """
            delta = parse(insert_time).replace(tzinfo=None) - datetime.utcfromtimestamp(0)
            return int(delta.total_seconds()) * 1000 + int(delta.microseconds / 1000)


@resources.register('sql-ssl-cert')
class SqlSslCert(SqlInstanceChildWithSelfLink):
    """GCP Resource
    https://cloud.google.com/sql/docs/mysql/admin-api/rest/v1beta4/sslCerts
    """
    class resource_type(SQLInstanceChildTypeInfo):
        component = 'sslCerts'
        enum_spec = ('list', 'items[]', None)
        get_requires_event = True
        id = 'sha1Fingerprint'
        name = "commonName"
        default_report_fields = [
            id, name, "instance", "expirationTime"]
        urn_component = "ssl-cert"

        @staticmethod
        def get(client, event):
            self_link = jmespath_search('protoPayload.response.clientCert.certInfo.selfLink', event)
            self_link_re = '.*?/projects/(.*?)/instances/(.*?)/sslCerts/(.*)'
            project, instance, sha_1_fingerprint = re.match(self_link_re, self_link).groups()
            parameters = {'project': project,
                          'instance': instance,
                          'sha1Fingerprint': sha_1_fingerprint}
            return client.execute_command('get', parameters)
