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
import pytest

from c7n.resources import load_resources
from .common import BaseTest


def get_doc_examples():
    policies = []
    names = []
    load_resources()
    for mod in sys.modules.keys():
        if 'c7n.resources' in mod:
            module = sys.modules[mod]
            for sub_item in dir(module):
                cls = getattr(sys.modules[mod], sub_item, None)
                if isinstance(cls, type):
                    if cls.__doc__:
                        splt_doc = cls.__doc__.split('yaml\n\n            ') # fix reget to catch all tests
                        if len(splt_doc) == 2:
                                # pp = yaml.load(splt_doc[1])
                                # p = self.load_policy(pp["policies"][0])
                            policies.append((splt_doc[1],))
                            names.append(cls.__name__)

    return policies, names



class DocExampleTest(BaseTest):

    policies_in_docs, names = get_doc_examples()
    policies_in_docs = ["x"]

    @pytest.mark.parametrize(['policy'], policies_in_docs,  scope="class")
    def test_doc_examples(self, policy):
        pol = yaml.load(policy)
        self.load_policy(pol)
        try:
            assert pol.validate()
            # print(p)
        except:
            assert 0
