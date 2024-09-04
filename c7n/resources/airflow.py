# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.filters.kms import KmsRelatedFilter
from c7n.tags import RemoveTag, Tag, TagDelayedAction, TagActionFilter
from c7n.actions import Action
from c7n.utils import local_session, type_schema


@resources.register('airflow')
class ApacheAirflow(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'mwaa'
        id = name = 'Name'
        enum_spec = ('list_environments', 'Environments', None)
        detail_spec = ('get_environment', 'Name', None, 'Environment')
        arn = 'Arn'
        arn_type = 'environment'
        cfn_type = 'AWS::MWAA::Environment'
        permission_prefix = 'airflow'

    permissions = (
        'airflow:GetEnvironment',
        'airflow:ListEnvironments',
    )

    def augment(self, resources):
        resources = super(ApacheAirflow, self).augment(resources)
        for r in resources:
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in r.get('Tags', {}).items()]
        return resources


@ApacheAirflow.filter_registry.register('kms-key')
class ApacheAirflowKmsFilter(KmsRelatedFilter):
    """

    Filter a Managed Workflow for Apache Airflow environment by its associcated kms key
    and optionally the aliasname of the kms key by using 'c7n:AliasName'

    :example:

    .. code-block:: yaml

        policies:
          - name: airflow-kms-key-filter
            resource: airflow
            filters:
              - type: kms-key
                key: c7n:AliasName
                value: alias/aws/mwaa
    """
    RelatedIdsExpression = 'KmsKey'


@ApacheAirflow.action_registry.register('tag')
class TagApacheAirflow(Tag):
    """Action to create tag(s) on a Managed Workflow for Apache Airflow environment

    :example:

    .. code-block:: yaml

            policies:
              - name: tag-airflow
                resource: airflow
                filters:
                  - "tag:target-tag": absent
                actions:
                  - type: tag
                    key: target-tag
                    value: target-tag-value
    """

    permissions = ('airflow:TagResource',)

    def process_resource_set(self, client, airflow, new_tags):
        for r in airflow:
            try:
                client.tag_resource(
                    ResourceArn=r['Arn'],
                    Tags={t['Key']: t['Value'] for t in new_tags})
            except client.exceptions.ResourceNotFound:
                continue


@ApacheAirflow.action_registry.register('remove-tag')
class UntagApacheAirflow(RemoveTag):
    """Action to remove tag(s) on a Managed Workflow for Apache Airflow environment

    :example:

    .. code-block:: yaml

            policies:
              - name: airflow-remove-tag
                resource: airflow
                filters:
                  - "tag:OutdatedTag": present
                actions:
                  - type: remove-tag
                    tags: ["OutdatedTag"]
    """

    permissions = ('airflow:UntagResource',)

    def process_resource_set(self, client, airflow, tags):
        for r in airflow:
            try:
                client.untag_resource(ResourceArn=r['Arn'], tagKeys=tags)
            except client.exceptions.ResourceNotFound:
                continue


ApacheAirflow.filter_registry.register('marked-for-op', TagActionFilter)
ApacheAirflow.action_registry.register('mark-for-op', TagDelayedAction)


@ApacheAirflow.action_registry.register('update-environment')
class UpdateApacheAirflowEnvironment(Action):
    """
    Action to update an Airflow environment to
    set the WebserverAccessMode to PRIVATE_ONLY or PUBLIC_ONLY.

    :example:

    .. code-block:: yaml

        policies:
          - name: set-webserver-access-mode
            resource: airflow
            actions:
              - type: update-environment
                access_mode: PRIVATE_ONLY
    """

    permissions = ('airflow:UpdateEnvironment',)

    schema = type_schema(
        'update-environment',
        access_mode={'type': 'string', 'enum': ['PRIVATE_ONLY', 'PUBLIC_ONLY']},
        required=['access_mode']
    )
    valid_origin_states = ('AVAILABLE', 'UPDATE_FAILED')

    def process(self, resources):
        resources = self.filter_resources(resources, 'Status', self.valid_origin_states)
        client = local_session(self.manager.session_factory).client('mwaa')
        access_mode = self.data.get('access_mode')
        for r in resources:
            self.process_environment(r, client, access_mode)

    def process_environment(self, r, client, access_mode):
        current_access_mode = r.get('WebserverAccessMode')
        if current_access_mode == access_mode:
            return
        client.update_environment(
            Name=r['Name'],
            WebserverAccessMode=access_mode
        )


@ApacheAirflow.action_registry.register('delete-environment')
class DeleteApacheAirflowEnvironment(Action):
    """
    Action to delete a Managed Workflow for Apache Airflow environment

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-airflow-environment
            resource: airflow
            actions:
              - type: delete-environment
    """

    permissions = ('airflow:DeleteEnvironment',)

    schema = type_schema('delete-environment')
    valid_origin_states = ('AVAILABLE', 'CREATE_FAILED', 'DELETE_FAILED',)

    def process(self, resources):
        resources = self.filter_resources(resources, 'Status', self.valid_origin_states)
        client = local_session(self.manager.session_factory).client('mwaa')
        for r in resources:
            self.manager.retry(
                client.delete_environment,
                Name=r["Name"],
                ignore_err_codes=("ResourceNotFoundException",)
            )
