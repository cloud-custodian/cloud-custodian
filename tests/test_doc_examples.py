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

import pytest

from c7n.config import Config
from c7n.loader import PolicyLoader
from c7n.provider import clouds
from c7n.resources import load_resources
from c7n.utils import yaml_load

from .common import BaseTest  # NOQA - loads providers for individual module testing


def get_doc_examples(resources):
    policies = []
    seen = set()
    for resource_name, v in resources.items():
        for k, cls in itertools.chain(v.filter_registry.items(), v.action_registry.items()):
            if cls in seen:
                continue
            seen.add(cls)
            if not cls.__doc__:
                continue
            # split on yaml and new lines
            split_doc = [x.split('\n\n') for x in cls.__doc__.split('yaml')]
            for item in itertools.chain.from_iterable(split_doc):
                if 'policies:\n' in item:
                    policies.append((item, resource_name, cls.type))
    return policies


def get_doc_policies(resources):
    """ Retrieve all unique policies from the list of resources.
    Duplicate policy is a policy that uses same name but has different set of
    actions and/or filters.

    Input a resource list.
    Returns policies map (name->policy) and a list of duplicate policy names.
    """
    policies = {}
    duplicate_names = set()
    for ptext, resource_name, el_name in get_doc_examples(resources):
        data = yaml_load(ptext)
        for p in data.get('policies', []):
            if p['name'] in policies:
                if policies[p['name']] != p:
                    duplicate_names.add(p['name'])
            else:
                policies[p['name']] = p

    if duplicate_names:
        print('If you see this error, there are some policies with the same name but different '
              'set of filters and/or actions.\n'
              'Please make sure you\'re using unique names for different policies.\n')
        print('Duplicate policy names:')
        for d in duplicate_names:
            print('\t{0}'.format(d))

    return policies, duplicate_names


skip_condition = not (
    # Okay slightly gross, basically if we're explicitly told via
    # env var to run doc tests do it.
    (os.environ.get("C7N_TEST_DOC") in ('yes', 'true') or
     # Or for ci to avoid some tox pain, we'll auto configure here
     # to run on the py3.6 test runner, as its the only one
     # without additional responsibilities.
     (os.environ.get('C7N_TEST_RUN') and
      sys.version_info.major == 2 and
      sys.version_info.minor == 7)))


@pytest.mark.skipif(skip_condition, reason="Doc tests must be explicitly enabled with C7N_DOC_TEST")
@pytest.mark.parametrize("provider_name", ('aws', 'azure', 'gcp', 'k8s'))
def test_doc_examples(provider_name):
    load_resources()
    loader = PolicyLoader(Config.empty())
    provider = clouds.get(provider_name)
    policies, duplicate_names = get_doc_policies(provider.resources)

    for p in policies.values():
        loader.load_data({'policies': [p]}, 'memory://')

    assert not duplicate_names

    for p in policies.values():
        # Note max name size here is 54 if it a lambda policy given
        # our default prefix custodian- to stay under 64 char limit on
        # lambda function names.  This applies to AWS and GCP, and
        # afaict Azure.
        if len(p['name']) >= 54 and 'mode' in p:
            raise ValueError(
                "doc policy exceeds name limit policy:%s" % (p['name']))
