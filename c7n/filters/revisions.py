# Copyright 2016 Capital One Services, LLC
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
"""
Custodian support for diffing and patching across multiple versions
of a resource.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from botocore.exceptions import ClientError
from dateutil.parser import parse as parse_date

from c7n.filters import Filter, FilterValidationError
from c7n.utils import local_session, type_schema


ErrNotFound = "ResourceNotDiscoveredException"


class Diff(Filter):
    """Compute the diff from the current resource to a previous version.

    A resource matches the filter if a diff exists between the current
    resource and the selected revision.

    Utilizes config as a resource revision database.

    Revisions can be selected by date, against the previous version, and
    against a locked version (requires use of is-locked filter).
    """

    schema = type_schema(
        'diff',
        selector={'enum': ['previous', 'date', 'locked']},
        # For date selectors allow value specification
        selector_value={'type': 'string'})

    permissions = ('config:GetResourceConfigHistory',)

    selector_value = mode = parser = resource_shape = None

    def validate(self):
        if 'selector' in self.data and self.data['selector'] == 'date':
            if 'selector_value' not in self.data:
                raise FilterValidationError(
                    "Date version selector requires specification of date")
            try:
                parse_date(self.data['selector_value'])
            except ValueError:
                raise FilterValidationError(
                    "Invalid date for selector_value")

        elif 'selector' in self.data and self.data['selector'] == 'locked':
            idx = self.manager.data['filters'].index(self.data)
            found = False
            for n in self.manager.data['filters'][:idx]:
                if isinstance(n, dict) and n.get('type', '') == 'is-locked':
                    found = True
                if isinstance(n, basestring) and n == 'is-locked':
                    found = True
            if not found:
                raise FilterValidationError(
                    "locked selector needs previous use of is-locked filter")
        return self

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)
        config = session.client('config')
        self.model = self.manager.get_model()

        results = []
        for r in resources:
            revisions = self.get_revisions(config, r)
            r['c7n:previous-revision'] = rev = self.select_revision(revisions)
            if not rev:
                continue
            delta = self.diff(rev['resource'], r)
            if delta:
                r['c7n:diff'] = delta
                results.append(r)
        return results

    def get_revisions(self, config, resource):
        params = dict(
            resourceType=self.model.config_type,
            resourceId=resource[self.model.id])
        params.update(self.get_selector_params(resource))
        try:
            revisions = config.get_resource_config_history(
                **params)['configurationItems']
        except ClientError as e:
            if e.response['Error']['Code'] != ErrNotFound:
                self.log.debug(
                    "config - resource %s:%s not found" % (
                        self.model.config_type, resource[self.model.id]))
                revisions = []
            raise
        return revisions

    def get_selector_params(self, resource):
        params = {}
        selector = self.data.get('selector', 'previous')
        if selector == 'date':
            if not self.selector_value:
                self.selector_value = parse_date(
                    self.data.get('selector_value'))
            params['laterTime'] = self.selector_value
            params['limit'] = 3
        elif selector == 'previous':
            params['limit'] = 2
        elif selector == 'locked':
            params['laterTime'] = resource.get('c7n:locked_date')
            params['limit'] = 2
        return params

    def select_revision(self, revisions):
        for rev in revisions:
            return {
                'date': rev['configurationItemCaptureTime'],
                'version_id': rev['configurationStateId'],
                'events': rev['relatedEvents'],
                'resource': self.transform_revision(rev)}

    def transform_revision(self, revision):
        """make config revision look like describe output."""
        raise NotImplementedError("subclass responsibility")

    def diff(self, source, target):
        raise NotImplementedError("Subclass responsibility")
