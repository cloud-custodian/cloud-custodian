import logging

from c7n.filters import ListItemFilter
from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager

log = logging.getLogger('custodian.azure.sql-managed-instance')


@resources.register('sql-managed-instance')
class SqlManagedInstance(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.sql'
        client = 'SqlManagementClient'
        enum_spec = ('managed_instances', 'list', None)
        resource_type = 'Microsoft.Sql/managedInstances'
        diagnostic_settings_enabled = False


@SqlManagedInstance.filter_registry.register('vulnerability-assessments')
class SqlManagedInstanceVulnerabilityAssessmentsFilter(ListItemFilter):
    """
    Filters managed instances by their vulnerability assessments

    :example:

    .. code-block:: yaml

        policies:
          - name: managed-instances-with-vulnerability-recurring-scan-enabled
            resource: azure.sql-managed-instance
            filters:
              - type: vulnerability-assessments
                attrs:
                  - type: value
                    key: properties.recurringScans.isEnabled
                    value: True

    """
    schema = type_schema(
        'vulnerability-assessments',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    item_annotation_key = 'c7n:VulnerabilityAssessments'
    annotate_items = True

    def get_item_values(self, resource):
        it = self.manager.get_client().managed_instance_vulnerability_assessments.list_by_instance(
            resource_group_name=resource['resourceGroup'],
            managed_instance_name=resource['name']
        )
        return [item.serialize(True) for item in it]


@SqlManagedInstance.filter_registry.register('encryption-protectors')
class SqlManagedInstanceEncryptionProtectorsFilter(ListItemFilter):
    """
    Filters resources by encryption protectors.

    :example:

    .. code-block:: yaml

        policies:
          - name: azure-sql-managed-instance-service-managed
            resource: azure.sql-managed-instance
            filters:
              - type: encryption-protectors
                attrs:
                  - type: value
                    key: properties.serverKeyType
                    value: ServiceManaged

    """

    schema = type_schema(
        'encryption-protectors',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    item_annotation_key = 'c7n:EncryptionProtectors'
    annotate_items = True

    def get_item_values(self, resource):
        it = self.manager.get_client().managed_instance_encryption_protectors.list_by_instance(
            resource_group_name=resource['resourceGroup'],
            managed_instance_name=resource['name']
        )
        return [item.serialize(True) for item in it]


@SqlManagedInstance.filter_registry.register('security-alert-policies')
class SqlManagedInstanceSecurityAlertPoliciesFilter(ListItemFilter):
    """
    Filters resources by managed server security alert policies'.

    :example:

    .. code-block:: yaml

        policies:
          - name: azure-sql-managed-server-security-alert-policies
            resource: azure.sql-managed-instance
            filters:
              - type: security-alert-policies
                attrs:
                  - type: value
                    key: properties.state
                    value: Disabled

    """

    schema = type_schema(
        'security-alert-policies',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    item_annotation_key = 'c7n:security-alert-policies'
    annotate_items = True

    def get_item_values(self, resource):
        it = self.manager.get_client().managed_server_security_alert_policies.list_by_instance(
            resource_group_name=resource['resourceGroup'],
            managed_instance_name=resource['name']
        )
        return [item.serialize(True) for item in it]
