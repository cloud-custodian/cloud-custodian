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
import sys
import yaml
from parameterized import parameterized
import itertools

from c7n.resources import load_resources
from c7n.exceptions import PolicyValidationError
from .common import BaseTest


def get_doc_examples(doc_folders):
    policies = []
    load_resources()
    for mod in sys.modules.keys():
        if any(doc_base in mod for doc_base in doc_folders):
            module = sys.modules[mod]
            for sub_item in dir(module):
                cls = getattr(sys.modules[mod], sub_item, None)
                if isinstance(cls, type):
                    if cls.__doc__:
                        split_doc = [x.split('\n\n ') for x in
                                     cls.__doc__.split('yaml')]  # split on yaml and new lines
                        for item in itertools.chain.from_iterable(split_doc):
                            if 'policies:\n' in item:
                                policies.append((item, module.__name__, cls.__name__))

    return policies


def custom_test_name(testcase_func, param_num, param):
    return "test_docs_%s_%s" % (
        param.args[1],
        param.args[2]
    )


class DocExampleTest(BaseTest):

    policies_in_docs = get_doc_examples(['c7n.resources', 'c7n_azure', 'c7n_gcp'])

    @parameterized.expand(policies_in_docs, name_func=custom_test_name)
    def test_doc_examples(self, policy, module, name):
        try:
            parsed_policy = yaml.load(policy)
            policy = self.load_policy(parsed_policy["policies"][0])
            self.assertIsNone(policy.validate())
        except PolicyValidationError:
            raise
