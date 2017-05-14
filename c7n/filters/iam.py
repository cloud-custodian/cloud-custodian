
# Copyright 2016-2017 Capital One Services, LLC
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

import csv
import datetime
import io
from datetime import timedelta
import itertools
import time
import jmespath

from c7n.filters import ValueFilter, Filter, OPERATORS
from c7n.filters.iampermissionsmanager import IamPermissionsManager
from c7n.utils import local_session, type_schema, chunks


class ActionEffectFilter(Filter):

    schema = type_schema('action-effect',
        effect={'type': 'string', 'enum': ['Allow', 'Deny', 'Unknown']},
        actions={'type': 'array', 'items': {'type': 'string'}},
        required=['effect', 'actions'])

    permissions = ('iam:ListUserPolicies', 'iam:ListAttachedUserPolicies',
        'iam:GetUserPolicy', 'iam:GetPolicy', 'iam:GetPolicyVersion')

    def statements_for_resource(self, resource, manager):
        raise NotImplementedError

    def match(self, resource, manager):
        statements = None
        if 'c7n:AllStatements' in resource:
            statements = manager.load(resource['c7n:AllStatements'])
        else:
            statements = self.statements_for_resource(resource, manager)
            resource['c7n:AllStatements'] = statements.serialize()

        expectedEffect = self.data['effect']
        actions = self.data['actions']

        matchedDetails = {}
        resource['c7n:ActionEffectMatched'] = matchedDetails

        for action in actions:
            (effect, matching) = statements.for_action(action)
            if effect == expectedEffect:
                matchedDetails['action'] = action
                matchedDetails['details'] = matching
                matchedDetails['effect'] = effect
                return True

        return False

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('iam')
        manager = IamPermissionsManager(client)
        # Filter where they match the given conditions.
        return filter(lambda r: self.match(r, manager), resources)

class RoleActionEffectFilter(ActionEffectFilter):

    schema = type_schema('role-action-effect', rinherit=ActionEffectFilter.schema)

    role_arn_selector = "RoleARN"
    selector_cache = {}

    def statements_for_resource(self, resource, manager):
        if not self.role_arn_selector in self.selector_cache:
            self.selector_cache[self.role_arn_selector] = jmespath.compile(self.role_arn_selector)

        role_arn = self.selector_cache[self.role_arn_selector].search(resource)
        return manager.for_role_arn(role_arn)
