# Copyright 2018 Capital One Services, LLC
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

from .core import Filter

from c7n.exceptions import PolicyValidationError
from c7n.utils import type_schema
from c7n.policy import Policy


class Missing(Filter):
    """Assert the absence of a particular resource.

    Intended for use at a logical account/subscription/project level

    This works as an effectively an embedded policy thats evaluated.
    """
    schema = type_schema(
        'missing', policy={'type': 'object'}, required=['policy'])

    def __init__(self, data, manager):
        super(Missing, self).__init__(data, manager)
        self.data['policy']['name'] = self.manager.ctx.policy.name
        self.embedded_policy = Policy(self.data['policy'], self.manager.config)

    def validate(self):
        if 'mode' in self.data['policy']:
            raise PolicyValidationError(
                "Execution mode can't be specified in "
                "embedded policy %s" % self.data)
        if 'actions' in self.data['policy']:
            raise PolicyValidationError(
                "Actions can't be specified in "
                "embedded policy %s" % self.data)

        self.embedded_policy.validate()
        return self

    def get_permissions(self):
        return self.embedded_policy.get_permissions()

    def process(self, resources, event=None):
        check_resources = self.embedded_policy.poll()
        if not check_resources:
            return resources
        return []
