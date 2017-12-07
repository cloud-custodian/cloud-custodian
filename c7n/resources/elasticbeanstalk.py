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

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.actions import BaseAction
from c7n.utils import type_schema
from c7n import utils


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


@ElasticBeanstalkEnvironment.action_registry.register('terminate')
class Terminate(BaseAction):
    """ Terminate an ElasticBeanstalk Environment.

    :Example:

    .. code-block: yaml

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
