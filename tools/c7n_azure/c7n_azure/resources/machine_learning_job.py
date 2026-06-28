# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager


@resources.register('machine-learning-job')
class MachineLearningJob(ChildArmResourceManager):
    """Azure Machine Learning Job Resource

    Jobs are child resources of a Machine Learning workspace
    (``Microsoft.MachineLearningServices/workspaces/jobs``). They are enumerated
    per workspace using the ``Jobs_List`` API.

    :example:

    Find sweep jobs whose maximum number of concurrent trials exceeds 10.

    .. code-block:: yaml

        policies:
          - name: ml-sweep-jobs-over-parallelism-limit
            resource: azure.machine-learning-job
            filters:
              - type: value
                key: properties.jobType
                value: Sweep
              - type: value
                key: properties.limits.maxConcurrentTrials
                op: gt
                value: 10

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        service = 'azure.mgmt.machinelearningservices'
        client = 'MachineLearningServicesMgmtClient'
        enum_spec = ('jobs', 'list', None)
        parent_manager_name = 'machine-learning-workspace'
        resource_type = 'Microsoft.MachineLearningServices/workspaces/jobs'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            '"c7n:parent-id"'
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': parent_resource['resourceGroup'],
                'workspace_name': parent_resource['name'],
            }
