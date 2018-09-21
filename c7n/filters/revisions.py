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
"""
Custodian support for diffing and patching across multiple versions
of a resource.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import six

from dateutil.parser import parse as parse_date
from dateutil.tz import tzlocal, tzutc

from c7n.exceptions import PolicyValidationError, ClientError
from c7n.filters import Filter
from c7n.manager import resources
from c7n.utils import local_session, type_schema

try:
    import jsonpatch
    HAVE_JSONPATH = True
except ImportError:
    HAVE_JSONPATH = False


ErrNotFound = "ResourceNotDiscoveredException"

UTC = tzutc()


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
                raise PolicyValidationError(
                    "Date version selector requires specification of date on %s" % (
                        self.manager.data))
            try:
                parse_date(self.data['selector_value'])
            except ValueError:
                raise PolicyValidationError(
                    "Invalid date for selector_value on %s" % (self.manager.data))

        elif 'selector' in self.data and self.data['selector'] == 'locked':
            idx = self.manager.data['filters'].index(self.data)
            found = False
            for n in self.manager.data['filters'][:idx]:
                if isinstance(n, dict) and n.get('type', '') == 'locked':
                    found = True
                if isinstance(n, six.string_types) and n == 'locked':
                    found = True
            if not found:
                raise PolicyValidationError(
                    "locked selector needs previous use of is-locked filter on %s" % (
                        self.manager.data))
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
            if e.response['Error']['Code'] == 'ResourceNotDiscoveredException':
                return []
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
            # convert unix timestamp to utc to be normalized with other dates
            if rev['configurationItemCaptureTime'].tzinfo and \
               isinstance(rev['configurationItemCaptureTime'].tzinfo, tzlocal):
                rev['configurationItemCaptureTime'] = rev[
                    'configurationItemCaptureTime'].astimezone(UTC)
            return {
                'date': rev['configurationItemCaptureTime'],
                'version_id': rev['configurationStateId'],
                'events': rev['relatedEvents'],
                'resource': self.transform_revision(rev)}

    def transform_revision(self, revision):
        """make config revision look like describe output."""
        config = self.manager.get_source('config')
        return config.load_resource(revision)

    def diff(self, source, target):
        raise NotImplementedError("Subclass responsibility")


class JsonDiff(Diff):

    schema = type_schema(
        'json-diff',
        selector={'enum': ['previous', 'date', 'locked']},
        # For date selectors allow value specification
        selector_value={'type': 'string'})

    def diff(self, source, target):
        source, target = (
            self.sanitize_revision(source), self.sanitize_revision(target))
        patch = jsonpatch.JsonPatch.from_diff(source, target)
        return list(patch)

    def sanitize_revision(self, rev):
        sanitized = dict(rev)
        for k in [k for k in sanitized if 'c7n' in k]:
            sanitized.pop(k)
        return sanitized

    @classmethod
    def register_resources(klass, registry, resource_class):
        """ meta model subscriber on resource registration.

        We watch for new resource types being registered and if they
        support aws config, automatically register the jsondiff filter.
        """
        config_type = getattr(resource_class.resource_type, 'config_type', None)
        if config_type is None:
            return
        resource_class.filter_registry.register('json-diff', klass)


if HAVE_JSONPATH:
    resources.subscribe(resources.EVENT_REGISTER, JsonDiff.register_resources)
