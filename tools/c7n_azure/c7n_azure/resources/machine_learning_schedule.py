# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from azure.core.exceptions import ResourceNotFoundError
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager

log = logging.getLogger('custodian.azure.machine_learning')


@resources.register('machine-learning-schedule')
class MachineLearningSchedule(ChildArmResourceManager):
    """Azure Machine Learning Schedule Resource

    Schedules are child resources of a Machine Learning workspace
    (``Microsoft.MachineLearningServices/workspaces/schedules``) that
    trigger a job or batch endpoint on a recurrence or cron trigger.
    Disabled schedules are included.

    :example:

    Find enabled schedules that create a job every minute or hour.

    .. code-block:: yaml

        policies:
          - name: ml-schedules-sub-daily-jobs
            resource: azure.machine-learning-schedule
            filters:
              - type: value
                key: properties.isEnabled
                value: true
              - type: value
                key: properties.action.actionType
                value: CreateJob
              - type: value
                key: properties.trigger.triggerType
                value: Recurrence
              - type: value
                key: properties.trigger.frequency
                op: in
                value:
                  - Minute
                  - Hour

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        service = 'azure.mgmt.machinelearningservices'
        client = 'MachineLearningServicesMgmtClient'
        enum_spec = ('schedules', 'list', None)
        parent_manager_name = 'machine-learning-workspace'
        resource_type = 'Microsoft.MachineLearningServices/workspaces/schedules'
        diagnostic_settings_enabled = False
        default_report_fields = (
            'name',
            'resourceGroup',
            '"c7n:parent-id"'
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': parent_resource['resourceGroup'],
                'workspace_name': parent_resource['name'],
                'list_view_type': 'All',
            }

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
        try:
            return super().enumerate_resources(
                parent_resource, type_info, vault_url=vault_url, **params)
        except ResourceNotFoundError as e:
            # A workspace stuck deleting is still listed after its resource group is gone.
            log.warning('Skipping Machine Learning workspace %s: %s', parent_resource['id'], e)
            return []
