# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import logging
import re

from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import BaseAction
from c7n.filters import Filter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema
from c7n.tags import RemoveTag, Tag

log = logging.getLogger('custodian.cfn')


@resources.register('cfn')
class CloudFormation(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'cloudformation'
        arn_type = 'stack'
        enum_spec = ('describe_stacks', 'Stacks[]', None)
        id = 'StackName'
        filter_name = 'StackName'
        filter_type = 'scalar'
        name = 'StackName'
        date = 'CreationTime'
        cfn_type = config_type = 'AWS::CloudFormation::Stack'


@CloudFormation.action_registry.register('delete')
class Delete(BaseAction):
    """Action to delete cloudformation stacks

    It is recommended to use a filter to avoid unwanted deletion of stacks

    If you enable the `force` option, it will automatically disable
    termination protection if required.  This is useful because you cannot
    filter on EnableTerminationProtection since that field is only
    included by AWS when the DescribeStacks API is called with a specific
    stack name or id.

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudformation-delete-failed-stacks
                resource: cfn
                filters:
                  - StackStatus: ROLLBACK_COMPLETE
                actions:
                  - type: delete
                    force: true
    """

    schema = type_schema('delete', force={'type': 'boolean', 'default': False})
    permissions = ('cloudformation:DeleteStack', 'cloudformation:UpdateStack')

    def process(self, stacks):
        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_stacks, stacks))

    def process_stacks(self, stack):
        client = local_session(self.manager.session_factory).client('cloudformation')
        try:
            self.manager.retry(client.delete_stack, StackName=stack['StackName'])
        except ClientError as e:
            code = e.response['Error']['Code']
            msg = e.response['Error']['Message']
            if (
                code == 'ValidationError'
                and 'cannot be deleted while TerminationProtection is enabled' in msg
            ):
                if self.data.get('force', False):
                    # forced delete, so disable termination protection and try again
                    self.manager.retry(
                        client.update_termination_protection,
                        EnableTerminationProtection=False,
                        StackName=stack['StackName'],
                    )
                    self.manager.retry(
                        client.delete_stack, StackName=stack['StackName']
                    )
                else:
                    # no force, so just log an error and move on
                    self.log.error(
                        'Error deleting stack:%s error:%s', stack['StackName'], msg,
                    )
            else:
                raise


@CloudFormation.action_registry.register('set-protection')
class SetProtection(BaseAction):
    """Action to disable termination protection

    It is recommended to use a filter to avoid unwanted deletion of stacks

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudformation-disable-protection
                resource: cfn
                filters:
                  - StackStatus: CREATE_COMPLETE
                actions:
                  - type: set-protection
                    state: False
    """

    schema = type_schema('set-protection', state={'type': 'boolean', 'default': False})

    permissions = ('cloudformation:UpdateStack',)

    def process(self, stacks):
        client = local_session(self.manager.session_factory).client('cloudformation')

        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for s in stacks:
                futures[w.submit(self.process_stacks, client, s)] = s
            for f in as_completed(futures):
                s = futures[f]
                if f.exception():
                    self.log.error(
                        'Error updating protection stack:%s error:%s',
                        s['StackName'],
                        f.exception(),
                    )

    def process_stacks(self, client, stack):
        self.manager.retry(
            client.update_termination_protection,
            EnableTerminationProtection=self.data.get('state', False),
            StackName=stack['StackName'],
        )


@CloudFormation.action_registry.register('tag')
class CloudFormationAddTag(Tag):
    """Action to tag a cloudformation stack

    :example:

    .. code-block:: yaml

        policies:
          - name: add-cfn-tag
            resource: cfn
            filters:
              - 'tag:DesiredTag': absent
            actions:
              - type: tag
                tags:
                  DesiredTag: DesiredValue
    """

    permissions = ('cloudformation:UpdateStack',)

    def process_resource_set(self, client, stacks, tags):
        for s in stacks:
            _tag_stack(client, s, add=tags)


def _tag_stack(client, s, add=(), remove=()):

    tags = {t['Key']: t['Value'] for t in s.get('Tags')}
    for t in remove:
        tags.pop(t, None)

    for t in add:
        tags[t['Key']] = t['Value']

    params = []
    for p in s.get('Parameters', []):
        params.append({'ParameterKey': p['ParameterKey'], 'UsePreviousValue': True})

    capabilities = []
    for c in s.get('Capabilities', []):
        capabilities.append(c)

    notifications = []
    for n in s.get('NotificationArns', []):
        notifications.append(n)

    client.update_stack(
        StackName=s['StackName'],
        UsePreviousTemplate=True,
        Capabilities=capabilities,
        Parameters=params,
        NotificationARNs=notifications,
        Tags=[{'Key': k, 'Value': v} for k, v in tags.items()],
    )


@CloudFormation.action_registry.register('remove-tag')
class CloudFormationRemoveTag(RemoveTag):
    """Action to remove tags from a cloudformation stack

    :example:

    .. code-block:: yaml

        policies:
          - name: remove-cfn-tag
            resource: cfn
            filters:
              - 'tag:DesiredTag': present
            actions:
              - type: remove-tag
                tags: ['DesiredTag']
    """
    def process_resource_set(self, client, stacks, keys):
        for s in stacks:
            _tag_stack(client, s, remove=keys)

@CloudFormation.filter_registry.register('template')
class CloudFormationTemplateFilter(Filter):
    """Filter CloudFormation stacks based on their template body

    This filter retrieves the CloudFormation template for each stack and
    searches for the regex pattern provided in the template

    :example:

    .. code-block:: yaml

        policies:
          - name: detect-api-keys-in-templates
            resource: cfn
            filters:
              - type: template
                query: API_KEY[0-9A-Z]

    :param query: The regular expression pattern to search for within the template
    :param change-set-name: The name of the change set to retrieve the template for
    :param template-stage: The stage of the template to retrieve ('Original' or 'Processed')
    """

    schema = type_schema(
        'template',
        required=['query'],
        query={'type': 'string'},
        change_set_name={'type': 'string'},
        template_stage={'type': 'string', 'enum': ['Original', 'Processed']}
    )
    permissions = ('cloudformation:GetTemplate',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('cloudformation')
        matched = []
        pattern = self.data.get('query')
        change_set_name = self.data.get('change_set_name', None)
        template_stage = self.data.get('template_stage', "Processed")

        regex = re.compile(pattern)

        for r in resources:
            stack_id = r['StackId']
            params = {'StackName': stack_id}

            if change_set_name:
                params['ChangeSetName'] = change_set_name

            if template_stage:
                params['TemplateStage'] = template_stage

            response = client.get_template(**params)
            template_body = response.get('TemplateBody')

            # Serialize TemplateBody to a string
            if isinstance(template_body, dict):
                template_body = json.dumps(template_body, indent=2)

            if regex.search(template_body):
                matched.append(r)

        return matched
