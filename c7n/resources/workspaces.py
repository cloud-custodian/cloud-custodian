# Copyright 2019 Capital One Services, LLC
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
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import functools

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.tags import universal_augment, register_universal_tags
from c7n.utils import generate_arn


@resources.register('workspaces')
class Workspace(QueryResourceManager):

    class resource_type(object):
        service = 'workspaces'
        enum_spec = ('describe_workspaces', 'Workspaces', None)
        type = 'workspace'
        name = id = dimension = 'WorkspaceId'
        filter_name = None

    augment = universal_augment
    _generate_arn = None

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn, 'workspaces', region=self.config.region,
                account_id=self.account_id, resource_type='workspace', separator='/')
        return self._generate_arn


register_universal_tags(Workspace.filter_registry, Workspace.action_registry)
