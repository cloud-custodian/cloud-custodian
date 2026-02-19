# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('monitoring-notification-channel')
class MonitoringNotificationChannel(QueryResourceManager):
    """
    GCP Cloud Monitoring Notification Channel

    https://cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.notificationChannels
    """

    class resource_type(TypeInfo):
        service = 'monitoring'
        version = 'v3'
        component = 'projects.notificationChannels'
        enum_spec = ('list', 'notificationChannels[]', None)
        scope_key = 'name'
        scope_template = 'projects/{}'
        name = id = 'name'
        default_report_fields = ["name", "displayName", "type", "enabled", "labels"]
        asset_type = "monitoring.googleapis.com/NotificationChannel"
        urn_component = "notification-channel"
        permissions = ('monitoring.notificationChannels.list',)

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get',
                {
                    'name': 'projects/{project_id}/notificationChannels/{id}'.format(
                        **resource_info
                    )
                },
            )
