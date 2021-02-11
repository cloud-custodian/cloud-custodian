# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('policyassignments')
class PolicyAssignments(ArmResourceManager):
    """Policy Assignment Resource

    :example:

    This policy will find all policy assignments named 'test-assignment' and delete them.

    .. code-block:: yaml

      policies:
        - name: remove-test-assignments
          resource: azure.policyassignments
          filters:
            - type: value
              key: properties.displayName
              value_type: normalize
              op: eq
              value: 'test-assignment'
          actions:
            - type: delete

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Subscription', 'Generic']

        service = 'azure.mgmt.resource.policy'
        client = 'PolicyClient'
        enum_spec = ('policy_assignments', 'list', None)
        resource_type = 'Microsoft.Authorization/policyAssignments'
        default_report_fields = (
            'name',
            'resourceGroup'
        )
