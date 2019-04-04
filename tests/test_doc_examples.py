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

from c7n.resources import load_resources
from c7n.exceptions import PolicyValidationError
from .common import BaseTest


def get_doc_examples():
    policies = []
    load_resources()
    for mod in sys.modules.keys():
        if 'c7n.resources' in mod:
            module = sys.modules[mod]
            for sub_item in dir(module):
                cls = getattr(sys.modules[mod], sub_item, None)
                if isinstance(cls, type):
                    if cls.__doc__:
                        splt_doc = cls.__doc__.split('yaml') # fix reget to catch all tests
                        if len(splt_doc) == 2:
                                # pp = yaml.load(splt_doc[1])
                                # p = self.load_policy(pp["policies"][0])
                            policies.append((splt_doc[1], module.__name__,cls.__name__))

    return policies


def custom_test_name(testcase_func, param_num, param):
    return "test_docs_%s_%s" % (
        param.args[1],
        param.args[2]

    )


class DocExampleTest(BaseTest):

    policies_in_docs = get_doc_examples()

    @parameterized.expand(policies_in_docs, name_func=custom_test_name)
    def test_doc_examples(self, policy, module, name):
        try:
            parsed_policy = yaml.load(policy)
            policy = self.load_policy(parsed_policy["policies"][0])
            self.assertIsNone(policy.validate())
        except PolicyValidationError:
            self.assertIsNone(None)
