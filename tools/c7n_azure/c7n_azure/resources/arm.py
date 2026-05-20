# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time

import requests

from c7n_azure import constants
from c7n_azure.actions.delete import DeleteAction
from c7n_azure.actions.lock import LockAction
from c7n_azure.actions.tagging import (AutoTagDate)
from c7n_azure.actions.tagging import Tag, AutoTagUser, RemoveTag, TagTrim, TagDelayedAction
from c7n_azure.filters import (CostFilter, MetricFilter, TagActionFilter,
                               DiagnosticSettingsFilter, PolicyCompliantFilter, ResourceLockFilter,
                               AzureOffHour, AzureOnHour)
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager, QueryMeta, ChildResourceManager, TypeInfo, \
    ChildTypeInfo, TypeMeta
from c7n_azure.utils import ResourceIdParser

# ARM resources which do not currently support tagging
# for database it is a C7N known issue (#4543)
arm_tags_unsupported = ['microsoft.network/dnszones/',
                        'microsoft.sql/servers/databases',
                        'microsoft.storage/storageaccounts/blobservices/containers',
                        'microsoft.cognitiveservices/accounts/deployments',
                        'microsoft.cognitiveservices/accounts/projects/connections']


class ArmTypeInfo(TypeInfo, metaclass=TypeMeta):
    # api client construction information for ARM resources
    id = 'id'
    name = 'name'
    diagnostic_settings_enabled = True
    default_report_fields = (
        'name',
        'location',
        'resourceGroup'
    )
    resource_type = None


class ArmResourceManager(QueryResourceManager, metaclass=QueryMeta):
    class resource_type(ArmTypeInfo):
        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        enum_spec = ('resources', 'list', None)

    def augment(self, resources):
        for resource in resources:
            if 'id' in resource:
                resource['resourceGroup'] = ResourceIdParser.get_resource_group(resource['id'])
        return resources

    def get_resources(self, resource_ids):
        resource_client = self.get_client('azure.mgmt.resource.ResourceManagementClient')
        data = [
            resource_client.resources.get_by_id(rid, self._session.resource_api_version(rid))
            for rid in resource_ids
        ]
        return self.augment([r.serialize(True) for r in data])

    def _arm_rest_get(self, url, params=None, timeout=30, max_retries=3):
        """Issue ARM REST GET requests with paging and basic retry behavior.

        Retries up to ``max_retries`` times for throttling/service-unavailable
        responses (429/503), matching the expected ARM manager retry posture.
        """
        session = self.get_session()
        session._initialize_session()
        token_scope = session.cloud_endpoints.endpoints.resource_manager + '.default'
        token = session.credentials.get_token(token_scope)
        headers = {
            'Authorization': f'Bearer {token.token}',
            'Content-Type': 'application/json'
        }

        values = []
        next_url = url
        next_params = dict(params or {})

        while next_url:
            attempt = 0
            while True:
                response = requests.get(
                    next_url,
                    headers=headers,
                    params=next_params if next_params else None,
                    timeout=timeout
                )

                if response.status_code in (429, 503) and attempt < max_retries:
                    retry_after = response.headers.get('retry-after')
                    if retry_after and retry_after.isdigit():
                        sleep_seconds = int(retry_after)
                    else:
                        sleep_seconds = constants.DEFAULT_RETRY_AFTER
                    time.sleep(sleep_seconds)
                    attempt += 1
                    continue

                response.raise_for_status()
                break

            payload = response.json()
            values.extend(payload.get('value', []))
            next_url = payload.get('nextLink')
            next_params = None

        return values

    def tag_operation_enabled(self, resource_type):
        return ArmResourceManager.generic_resource_supports_tagging(resource_type)

    @staticmethod
    def generic_resource_supports_tagging(resource_type):
        return not resource_type.lower().startswith(tuple(arm_tags_unsupported))

    @staticmethod
    def register_arm_specific(registry, resource_class):

        if not issubclass(resource_class, ArmResourceManager):
            return

        # Register tag actions for everything except a few non-compliant resources
        if ArmResourceManager.generic_resource_supports_tagging(
                resource_class.resource_type.resource_type):
            resource_class.action_registry.register('tag', Tag)
            resource_class.action_registry.register('untag', RemoveTag)
            resource_class.action_registry.register('auto-tag-user', AutoTagUser)
            resource_class.action_registry.register('auto-tag-date', AutoTagDate)
            resource_class.action_registry.register('tag-trim', TagTrim)
            resource_class.filter_registry.register('marked-for-op', TagActionFilter)
            resource_class.action_registry.register('mark-for-op', TagDelayedAction)

        if resource_class.type != 'armresource':
            resource_class.filter_registry.register('cost', CostFilter)

        resource_class.filter_registry.register('metric', MetricFilter)
        resource_class.filter_registry.register('policy-compliant', PolicyCompliantFilter)
        resource_class.filter_registry.register('resource-lock', ResourceLockFilter)
        resource_class.action_registry.register('lock', LockAction)
        resource_class.filter_registry.register('offhour', AzureOffHour)
        resource_class.filter_registry.register('onhour', AzureOnHour)

        resource_class.action_registry.register('delete', DeleteAction)

        if resource_class.resource_type.diagnostic_settings_enabled:
            resource_class.filter_registry.register('diagnostic-settings', DiagnosticSettingsFilter)


class ChildArmResourceManager(ChildResourceManager, ArmResourceManager, metaclass=QueryMeta):

    class resource_type(ChildTypeInfo, ArmTypeInfo):
        pass


resources.subscribe(ArmResourceManager.register_arm_specific)
