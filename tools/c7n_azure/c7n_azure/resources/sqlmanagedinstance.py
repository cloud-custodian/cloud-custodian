import logging

from c7n_azure.filters import ValueFilter
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n.filters import Filter
from c7n.utils import type_schema
from c7n.vendored.distutils.util import strtobool

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
class SqlManagedInstanceEncryptionProtectorsFilter(Filter):
    """
    Filters resources by encryption protectors.

    :example:

    .. code-block:: yaml

        policies:
          - name: azure-sql-managed-instance-service-managed
            resource: azure.sql-managed-instance
            filters:
              - type: encryption-protector
                key: kind
                value: servicemanaged
    """

    schema = type_schema(
        'encryption-protector', rinherit=ValueFilter.schema
    )

    def __call__(self, resource):
        return resource

    @staticmethod
    def filter_by_encryption_protector(protectors, filtering_properties, value):
        add_to_filtered = False
        for protector in protectors:
            protector = protector.as_dict()
            property_value = protector
            for filtering_property in filtering_properties:
                if filtering_property in property_value:
                    property_value = property_value[filtering_property]
                else:
                    property_value = None
                    break
            if isinstance(property_value, bool) and isinstance(value, str):
                value = bool(strtobool(value))
            if value == property_value:
                add_to_filtered = True
                break
        return add_to_filtered

    def process(self, resources, event=None):
        client = self.manager.get_client('azure.mgmt.sql.SqlManagementClient')

        filtered_resources = []
        key = self.data['key']
        value = self.data['value']
        filtering_properties = key.split('.')
        for resource in resources:
            protectors = client.managed_instance_encryption_protectors.list_by_instance(
                resource['resourceGroup'],
                resource['name']
            )
            add_to_filtered = self.filter_by_encryption_protector(
                protectors, filtering_properties, value)

            if add_to_filtered:
                filtered_resources.append(resource)

        return super(SqlManagedInstanceEncryptionProtectorsFilter, self).process(
            filtered_resources, event)


@SqlManagedInstance.filter_registry.register('security-alert-policies')
class SqlManagedInstanceSecurityAlertPoliciesFilter(Filter):
    """
    Filters resources by managed server security alert policies'.

    :example:

    .. code-block:: yaml

        policies:
          - name: azure-sql-managed-server-security-alert-policies
            resource: azure.sql-managed-instance
            filters:
              - type: security-alert-policies
                key: state
                value: Disabled
    """

    schema = type_schema(
        'security-alert-policies', rinherit=ValueFilter.schema
    )

    def __call__(self, resource):
        return resource

    @staticmethod
    def filter_by_security_alert_policies(security_alert_policies, filtering_properties, value):
        add_to_filtered = False
        for security_alert_policy in security_alert_policies:
            security_alert_policy = security_alert_policy.as_dict()
            property_value = security_alert_policy
            for filtering_property in filtering_properties:
                if filtering_property in property_value:
                    property_value = property_value[filtering_property]
                else:
                    property_value = None
                    break
            if isinstance(property_value, bool) and isinstance(value, str):
                value = bool(strtobool(value))
            if value == property_value:
                add_to_filtered = True
                break
        return add_to_filtered

    def process(self, resources, event=None):
        client = self.manager.get_client('azure.mgmt.sql.SqlManagementClient')

        filtered_resources = []
        key = self.data['key']
        value = self.data['value']
        filtering_properties = key.split('.')
        for resource in resources:
            security_alert_policies = (
                client.managed_server_security_alert_policies.list_by_instance(
                    resource['resourceGroup'],
                    resource['name']))
            add_to_filtered = self.filter_by_security_alert_policies(
                security_alert_policies, filtering_properties, value)

            if add_to_filtered:
                filtered_resources.append(resource)

        return super(SqlManagedInstanceSecurityAlertPoliciesFilter, self).process(
            filtered_resources, event)
