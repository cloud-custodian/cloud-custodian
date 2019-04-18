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
import itertools
import os
import sys
import yaml

from c7n.provider import resources
from .common import BaseTest

try:
    import pytest
    skipif = pytest.mark.skipif
except ImportError:
    skipif = lambda func, reason="": func  # noqa E731


def get_doc_examples():
    policies = []
    for resource_name, v in resources().items():
        for k, cls in itertools.chain(v.filter_registry.items(), v.action_registry.items()):
            if not cls.__doc__:
                continue
            # split on yaml and new lines
            split_doc = [x.split('\n\n') for x in cls.__doc__.split('yaml')]
            for item in itertools.chain.from_iterable(split_doc):
                if 'policies:\n' in item:
                    policies.append((item, resource_name, cls.type))
    return policies


class DocExampleTest(BaseTest):

    skip_condition = not (
        # Okay slightly gross, basically if we're explicitly told via
        # env var to run doc tests do it.
        (os.environ.get("C7N_TEST_DOC") in ('yes', 'true') or
         # Or for ci to avoid some tox pain, we'll auto configure here
         # to run on the py3.6 test runner, as its the only one
         # without additional responsibilities.
         (os.environ.get('C7N_TEST_RUN') and
          sys.version_info.major == 3 and
          sys.version_info.minor == 6)))

    @skipif(skip_condition, reason="Doc tests must be explicitly enabled with C7N_DOC_TEST")
    def test_doc_examples(self):
        policies = []
        policy_map = {}
        idx = 1
        for ptext, resource_name, el_name in get_doc_examples():
            data = yaml.safe_load(ptext)
            for p in data.get('policies', []):
                # We unique based on name and content to avoid duplicates
                # from inherited docs.
                if p['name'] in policy_map:
                    if p != policy_map[p['name']]:
                        # Give each policy a unique name with enough
                        # context that we can identify the origin on
                        # failures.
                        p['name'] = "%s-%s-%s-%d" % (
                            resource_name.split('.')[-1],
                            el_name,
                            p.get('name', 'unknown'), idx)
                    continue
                policy_map[p['name']] = p
                # Note max name size here is 54 if its a lambda policy
                # given our default prefix custodian- to stay under 64
                # char limit on lambda function names.
                if len(p['name']) >= 54 and 'mode' in p:
                    raise ValueError(
                        "doc policy exceeds name limit resource:%s element:%s policy:%s" % (
                            resource_name, el_name, p['name']))
                policies.append(p)
                idx += 1
        self.load_policy_set({'policies': policies})
