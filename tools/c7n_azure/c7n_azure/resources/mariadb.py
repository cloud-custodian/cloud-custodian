# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('mariadb')
class MariaDB(ArmResourceManager):
    """Azure MariaDB Server Resource

    :example:

    Returns all MariaDB servers sslEnforcement not equal to Enabled

    .. code-block:: yaml

        policies:
          - name: mariabd-servers-enabled-with-ssl-enforcement
            resource: azure.mariadb
            filters:
              - type: value
                key: properties.sslEnforcement
                op: ne
                value: Enabled

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.rdbms.mariadb'
        client = 'MariaDBManagementClient'
        enum_spec = ('servers', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.DBForMariaDB/servers'
