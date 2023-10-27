
import logging

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager


log = logging.getLogger('custodian.azure.sql-server-vulnerability-assessments')


@resources.register('sql-server-vulnerability-assessments')
class SqlServerVulnerabilityAssessments(ChildArmResourceManager):
    """SQL Server Vulnerability Assessments

    The ``azure.sql-server-vulnerability-assessments`` resource is a child
    resource of the SQL Server resource.
    See also vulnerability-assessments filter for SqlServer.

    :example:

    Finds SQL Servers Vulnerability Assessments in the subscription.

    .. code-block:: yaml

        policies:
            - name: all-sql-server-vulnerability-assessments
              resource: azure.sql-server-vulnerability-assessments
            - name: sql-server-vulnerability-assessments-without-recurring-scans
              resource: azure.sql-server-vulnerability-assessments
              filters:
                  - type: value
                    key: properties.recurringScans.isEnabled
                    value: False
            - name: sql-server-vulnerability-assessments-with-recurring-scans
              resource: azure.sql-server-vulnerability-assessments
              filters:
                  - type: value
                    key: properties.recurringScans.isEnabled
                    value: True
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.sql'
        client = 'SqlManagementClient'
        enum_spec = ('vulnerabilityAssessments', 'list_by_server', None)
        parent_manager_name = 'sqlserver'
        resource_type = 'Microsoft.Sql/servers/vulnerabilityAssessments'

        @classmethod
        def extra_args(cls, parent_resource):
            return {'resource_group_name': parent_resource['resourceGroup'],
                    'server_name': parent_resource['name']}
