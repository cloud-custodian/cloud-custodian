# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import botocore.exceptions

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry
from c7n.filters import ValueFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import (
    type_schema, local_session)
from c7n.tags import universal_augment

MAX_RETRY_COUNT = 10

logger = logging.getLogger('custodian.redshift-param-group')

pg_filters = FilterRegistry('redshift-param-group.filters')
pg_actions = ActionRegistry('redshift-param-group.actions')


@resources.register('redshift-param-group')
class RedshiftParamGroup(QueryResourceManager):
    """Resource manager for Redshift parameter groups.
    """

    class resource_type(TypeInfo):
        service = 'redshift'
        arn_separator = ":"
        enum_spec = ('describe_cluster_parameter_groups', 'ParameterGroups', None)
        name = id = 'ParameterGroupName'
        filter_name = 'ParameterGroupName'
        filter_type = 'scalar'
        date = 'ClusterCreateTime'
        dimension = 'ParameterGroupName'
        cfn_type = config_type = "AWS::Redshift::ClusterParameterGroup"

    augment = universal_augment

    filter_registry = pg_filters
    action_registry = pg_actions


@pg_filters.register('check-require-ssl-status')
class CheckRequireSSLStatusFilter(ValueFilter):
    """
       This filter checks for parameter group with parameter require_ssl is set as true or not
       :example:
       .. code-block:: yaml

           filters:
             - type: check-require-ssl-status
       """
    schema = type_schema('check-require-ssl-status')

    def process(self, cluster_parameter_groups, event=None):
        redshift_client = local_session(self.manager.session_factory).client('redshift')
        results = []
        for pg in cluster_parameter_groups:
            parameter_group_name = pg.get('ParameterGroupName')
            if "default.redshift" in parameter_group_name:
                continue
            if self.should_modify_parameter(redshift_client, parameter_group_name):
                logger.info(f"Policy should modify parameter group: {parameter_group_name}")
                results.append(parameter_group_name)
        return results

    def should_modify_parameter(self, redshift_client, parameter_group_name):
        """
            This method checks if require_ssl parameter should be updated or not.

            Args:
                redshift_client: Authenticated redshift client
                parameter_group_name: The unique parameter group name

            Returns:
               a boolean, true if we should modify the parameter group
        """
        try:
            cluster_parameters_list = redshift_client.describe_cluster_parameters(
                ParameterGroupName=parameter_group_name
            ).get('Parameters')
        except botocore.exceptions.ClientError:
            raise

        for parameter_details in cluster_parameters_list:
            parameter_name = parameter_details.get('ParameterName')
            parameter_value = parameter_details.get('ParameterValue')
            if parameter_name == 'require_ssl' and parameter_value == 'true':
                logger.info("No need to modify parameter require_ssl")
                return False
        return True


@pg_actions.register('enable-require-ssl-parameter-group')
class EnableRequireSSLParameterGroup(BaseAction):
    """
    This action allows for updating parameter group with parameter require_ssl as true
    :example:
    .. code-block:: yaml

        actions:
          - type: enable-require-ssl-parameter-group
    """
    schema = type_schema('enable-require-ssl-parameter-group')

    def process(self, parameter_group_names):
        redshift_client = local_session(self.manager.session_factory).client('redshift')
        for pg in parameter_group_names:
            return self.process_update_parameter_group(redshift_client, pg)

    def process_update_parameter_group(self, redshift_client, parameter_group_name):
        """
        This method first calls modify_cluster_parameter_group to enforce require_ssl.
        Then, reboots all the clusters which have this parameter group
        Args:
            redshift_client: Authenticated redshift client
            parameter_group_name: Unique redshift parameter group name
        """
        self.enable_ssl_in_parameter_group(redshift_client, parameter_group_name)

    def enable_ssl_in_parameter_group(self, redshift_client, parameter_group_name):
        """
            Enables the SSL parameter in the redshift parameter group.

            Args:
                redshift_client: Authenticated redshift client
                parameter_group_name: The name of the redshift parameter group being updated

            Returns:
                None
        """
        logger.info("Enabling SSL for parameter group: %s.", parameter_group_name)
        try:
            response = redshift_client.modify_cluster_parameter_group(
                ParameterGroupName=parameter_group_name,
                Parameters=[
                    {
                        'ParameterName': 'require_ssl',
                        'ParameterValue': 'true'
                    }
                ]
            )
        except Exception as ex:
            logger.error(str(ex))

