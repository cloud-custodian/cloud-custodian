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
import yaml
import itertools
import os

from c7n.provider import resources
from .common import BaseTest

C7N_TEST_DOCS = bool(os.environ.get("C7N_TEST_DOCS", False))


def get_doc_examples():
    policies = []
    for key, v in resources().items():
        for k, cls in itertools.chain(v.filter_registry.items(), v.action_registry.items()):
            if cls.__doc__:
                split_doc = [x.split('\n\n') for x in
                             cls.__doc__.split('yaml')]  # split on yaml and new lines
                for item in itertools.chain.from_iterable(split_doc):
                    if 'policies:\n' in item:
                        policies.append((item, key, cls.__name__))

    return policies


class DocExampleTest(BaseTest):

    def test_doc_examples(self):
        errors = []
        for policy, module, cls_name in get_doc_examples():
            try:
                parsed_policy = yaml.safe_load(policy)
                list(map(lambda p: self.load_policy(p, validate=C7N_TEST_DOCS),
                         parsed_policy["policies"]))
            except Exception as e:
                errors.append((module, cls_name, e))

        assert len(errors) == 0, errors
