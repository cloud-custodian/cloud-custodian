# Copyright 2015-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

from botocore.exceptions import ClientError
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n import utils
from c7n import tags
from c7n.utils import get_retry, local_session, type_schema
from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry

log = logging.getLogger('custodian.elasticbeanstalk')

env_filters = FilterRegistry('elasticbeanstalk-environment.filters')
env_actions = ActionRegistry('elasticbeanstalk-environment.actions')

env_filters.register('tag-count', tags.TagCountFilter)
env_filters.register('marked-for-op', tags.TagActionFilter)


@resources.register('elasticbeanstalk')
class ElasticBeanstalk(QueryResourceManager):

    class resource_type(object):
        service = 'elasticbeanstalk'
        enum_spec = ('describe_applications', 'Applications', None)
        name = "ApplicationName"
        id = "ApplicationName"
        dimension = None
        default_report_fields = (
            'ApplicationName',
            'DateCreated',
            'DateUpdated'
        )
        filter_name = 'ApplicationNames'
        filter_type = 'list'


@resources.register('elasticbeanstalk-environment')
class ElasticBeanstalkEnvironment(QueryResourceManager):
    """ Resource manager for Elasticbeanstalk Environments
    """

    class resource_type(object):
        service = 'elasticbeanstalk'
        enum_spec = ('describe_environments', 'Environments', None)
        name = id = "EnvironmentName"
        dimension = None
        default_report_fields = (
            'EnvironmentName',
            'DateCreated',
            'DateUpdated',
        )
        filter_name = 'EnvironmentNames'
        filter_type = 'list'

    filter_registry = env_filters
    action_registry = env_actions
    retry = staticmethod(get_retry(('ThrottlingException',)))
    permissions = ('elasticbeanstalk:ListTagsForResource',)

    def augment(self, envs):
        filter(None, _eb_env_tags(
            envs, self.session_factory, self.executor_factory, self.retry
        ))
        return envs


def _eb_env_tags(envs, session_factory, executor_factory, retry):
    """Augment ElasticBeanstalk Environments with their tags."""

    def process_tags(eb_env):
        client = local_session(session_factory).client('elasticbeanstalk')
        try:
            tag_list = retry(
                client.list_tags_for_resource,
                ResourceArn=eb_env['EnvironmentArn']
            )['ResourceTags']
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                log.warning(
                    "Exception getting elasticbeanstalk-environment tags for "
                    "environment name: %s\n %s", eb_env['EnvironmentName'], e
                )
            return None
        eb_env['Tags'] = tag_list
        return eb_env

    # Handle API rate-limiting, which is a problem for accounts with many
    # EB Environments
    with executor_factory(max_workers=1) as w:
        return list(w.map(process_tags, envs))


@env_actions.register('mark-for-op')
class TagDelayedAction(tags.TagDelayedAction):
    """Mark an ElasticBeanstalk Environment for specific custodian action

    Note that this will cause an update to the environment to deploy the tag
    changes to all resources.

    :example:

    .. code-block:: yaml

            policies:
              - name: mark-for-delete
                resource: elasticbeanstalk-environment
                filters:
                  - type: value
                    key: CNAME
                    op: regex
                    value: .*inactive.*
                actions:
                  - type: mark-for-op
                    op: terminate
                    days: 7
    """
    schema = type_schema('mark-for-op', rinherit=tags.TagDelayedAction.schema)
    permissions = ('elasticbeanstalk:UpdateTagsForResource',)

    batch_size = 5

    def process(self, envs):
        return super(TagDelayedAction, self).process(envs)

    def process_resource_set(self, envs, tags):
        client = local_session(
            self.manager.session_factory
        ).client('elasticbeanstalk')
        for env in envs:
            client.update_tags_for_resource(
                ResourceArn=env['EnvironmentArn'],
                TagsToAdd=tags
            )


@env_actions.register('tag')
class Tag(tags.Tag):
    """Tag an ElasticBeanstalk Environment with a key/value

    Note that this will cause an update to the environment to deploy the tag
    changes to all resources.

    :example:

    .. code-block:: yaml

            policies:
              - name: eb-env-tag-owner-tag
                resource: elasticbeanstalk-environment
                filters:
                  - "tag:OwnerName": absent
                actions:
                  - type: tag
                    key: OwnerName
                    value: OwnerName
    """

    batch_size = 5
    permissions = ('elasticbeanstalk:UpdateTagsForResource',)

    def process_resource_set(self, envs, ts):
        client = local_session(
            self.manager.session_factory
        ).client('elasticbeanstalk')
        for env in envs:
            client.update_tags_for_resource(
                ResourceArn=env['EnvironmentArn'],
                TagsToAdd=ts
            )


@env_actions.register('remove-tag')
class RemoveTag(tags.RemoveTag):
    """Removes a tag or set of tags from ElasticBeanstalk Environments

    Note that this will cause an update to the environment to deploy the tag
    changes to all resources.

    :example:

    .. code-block:: yaml

            policies:
              - name: eb-env-unmark
                resource: elasticbeanstalk-environment
                filters:
                  - "tag:ExpiredTag": present
                actions:
                  - type: remove-tag
                    tags: ["ExpiredTag"]
    """

    batch_size = 5
    permissions = ('elasticbeanstalk:UpdateTagsForResource',)

    def process_resource_set(self, envs, tag_keys):
        client = local_session(
            self.manager.session_factory
        ).client('elasticbeanstalk')
        for env in envs:
            client.update_tags_for_resource(
                ResourceArn=env['EnvironmentArn'],
                TagsToRemove=tag_keys
            )


@env_actions.register('terminate')
class Terminate(BaseAction):
    """ Terminate an ElasticBeanstalk Environment.

    :Example:

    .. code-block:: yaml

        policies:
          - name: eb-env-termination
            resource: elasticbeanstalk-environment
            filters:
              - type: marked-for-op
                op: terminate
            actions:
              - terminate
    """

    schema = type_schema(
        'terminate',
        force={'type': 'boolean', 'default': False},
        terminate_resources={'type': 'boolean', 'default': True}
    )
    permissions = ("elasticbeanstalk:TerminateEnvironment",)

    def process(self, envs):
        force_terminate = self.data.get('force', False)
        terminate_resources = self.data.get('terminate_resources', True)
        client = utils.local_session(
            self.manager.session_factory).client('elasticbeanstalk')
        for e in envs:
            client.terminate_environment(
                EnvironmentName=e["EnvironmentName"],
                TerminateResources=terminate_resources,
                ForceTerminate=force_terminate
            )
