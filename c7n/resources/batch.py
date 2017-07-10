# Copyright 2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('batch-compute')
class ComputeEnvironment(QueryResourceManager):

    class resource_type(object):
        service = 'batch'
        filter_name = 'computeEnvironments'
        filter_type = 'list'
        dimension = None
        id = name = "computeEnvironmentName"
        enum_spec = (
            'describe_compute_environments', 'computeEnvironments', None)


@resources.register('batch-definition')
class JobDefinition(QueryResourceManager):

    class resource_type(object):
        service = 'batch'
        filter_name = 'jobDefinitions'
        filter_type = 'list'
        dimension = None
        id = name = "jobDefinitionName"
        enum_spec = (
            'describe_job_definitions', 'jobDefinitions', None)
