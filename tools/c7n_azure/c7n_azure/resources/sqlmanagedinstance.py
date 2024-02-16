import logging

from c7n.filters import ListItemFilter
from c7n.utils import type_schema
from c7n_azure.filters import ValueFilter
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


@SqlManagedInstance.filter_registry.register('vulnerability-assessment')
class SqlManagedInstanceVulnerabilityAssessmentsFilter(ValueFilter):
    schema = type_schema(
        'vulnerability-assessment',
        rinherit=ValueFilter.schema,
    )

    def __init__(self, data, manager=None):
        super(SqlManagedInstanceVulnerabilityAssessmentsFilter, self).__init__(data, manager)
        self.key = 'c7n:vulnerability_assessment'

    def process(self, resources, event=None):
        client = self.manager.get_client()
        key = self.key
        for resource in resources:
            if key in resource:
                continue
            # probably there can be only one of them. Oh, god bless azure api
            assessment = next(client.managed_instance_vulnerability_assessments.list_by_instance(
                resource_group_name=resource['resourceGroup'],
                managed_instance_name=resource['name']
            ), None)
            if assessment:
                resource[key] = assessment.serialize(True).get('properties') or {}
            else:
                resource[key] = {}
        return super(SqlManagedInstanceVulnerabilityAssessmentsFilter, self).process(resources, event)

    def __call__(self, resource):
        return super(SqlManagedInstanceVulnerabilityAssessmentsFilter, self).__call__(resource[self.key])


@SqlManagedInstance.filter_registry.register('encryption-protector')
class SqlManagedInstanceEncryptionProtectorsFilter(ValueFilter):
    """
    Filters resources by encryption protectors.

    :example:

    .. code-block:: yaml

        policies:
          - name: azure-sql-managed-instance-service-managed
            resource: azure.sql-managed-instance
            filters:
              - type: encryption-protector
                key: serverKeyType
                value: ServiceManaged
    """

    schema = type_schema(
        'encryption-protector', rinherit=ValueFilter.schema
    )

    def __init__(self, data, manager=None):
        super(SqlManagedInstanceEncryptionProtectorsFilter, self).__init__(data, manager)
        self.key = 'c7n:encryption_protector'

    def process(self, resources, event=None):
        client = self.manager.get_client()
        key = self.key
        for resource in resources:
            if key in resource:
                continue
            # probably there can be only one of them. Oh, god bless azure api
            protector = next(client.managed_instance_encryption_protectors.list_by_instance(
                resource_group_name=resource['resourceGroup'],
                managed_instance_name=resource['name']
            ), None)
            if protector:
                resource[key] = protector.serialize(True).get('properties') or {}
            else:
                resource[key] = {}
        return super(SqlManagedInstanceEncryptionProtectorsFilter, self).process(resources, event)

    def __call__(self, resource):
        return super(SqlManagedInstanceEncryptionProtectorsFilter, self).__call__(resource[self.key])


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
                    key: state
                    value: Disabled
    """

    schema = type_schema(
        'security-alert-policies',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    annotation_key = 'c7n:security-alert-policies'
    annotate_items = True

    def get_item_values(self, resource):
        it = self.manager.get_client().managed_server_security_alert_policies.list_by_instance(
            resource_group_name=resource['resourceGroup'],
            managed_instance_name=resource['name']
        )
        return [item.serialize(True) for item in it]
