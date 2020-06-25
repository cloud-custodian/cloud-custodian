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

import json
import os

from gcp_common import BaseTest
from c7n.config import Bag, Config
from c7n.resources import load_resources
from c7n_gcp.provider import resources


ALLOWED_NOPERM = set((
    'or', 'and', 'not', 'value', 'reduce',
    'offhour', 'onhour', 'marked-for-op',
    'event', 'webhook'))


class ResourceMetaTest(BaseTest):

    def test_check_permissions(self):
        load_resources(('gcp.*',))
        missing = []
        invalid = []
        iam_path = os.path.join(
            os.path.dirname(__file__), 'data', 'iam-permissions.json')
        with open(iam_path) as fh:
            valid_perms = set(json.load(fh).get('permissions'))
        cfg = Config.empty()

        for k, v in resources.items():
            policy = Bag({'name': 'permcheck',
                     'resource': 'gcp.%s' % k,
                     'provider_name': 'gcp'})
            ctx = self.get_context(config=cfg, policy=policy)
            mgr = v(ctx, policy)
            perms = mgr.get_permissions()
            if not perms:
                missing.append(k)
            for p in perms:
                if p not in valid_perms:
                    invalid.append((k, p))

            for n, a in list(v.action_registry.items()):
                if n in ALLOWED_NOPERM:
                    continue
                policy['actions'] = [n]
                perms = a({}, mgr).get_permissions()
                if not perms:
                    missing.append('%s.actions.%s' % (k, n))
                for p in perms:
                    if p not in valid_perms:
                        invalid.append(('%s.actions.%s' % (k, n), p))

            for n, f in list(v.filter_registry.items()):
                if n in ALLOWED_NOPERM:
                    continue
                policy['filters'] = [n]
                perms = f({}, mgr).get_permissions()
                if not perms:
                    missing.append('%s.filters.%s' % (k, n))
                for p in perms:
                    if p not in valid_perms:
                        invalid.append(('%s.filters.%s' % (k, n), p))

        if missing:
            self.fail('missing permissions %d on \n\t%s' % (
                len(missing), '\n\t'.join(sorted(missing))))

        if invalid:
            self.fail('invalid permissions %d on \n\t%s' % (
                len(invalid), '\n\t'.join(
                    map(str, sorted(invalid)))))

    def test_get_permissions(self):
        p = self.load_policy(
            {'name': 'istop',
             'resource': 'gcp.instance',
             'filters': [{'name': 'instance-1'}, {'status': 'RUNNING'}],
             'actions': ['stop']})
        self.assertEqual(
            p.get_permissions(),
            {'compute.instances.list', 'compute.instances.stop'})

    def test_resource_id_meta(self):
        load_resources(('gcp.*',))
        missing = []
        for name, resource in resources.items():
            if not getattr(resource.resource_type, 'id', None):
                missing.append(name)

        if missing:
            raise KeyError(
                "Following resources are missing id metadata %s" % " ".join(missing))
