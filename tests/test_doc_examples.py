# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import itertools
import pytest

from c7n.config import Config
from c7n.loader import PolicyLoader
from c7n.provider import clouds
from c7n.resources import load_resources
from c7n.schema import ElementSchema
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

            doc = ElementSchema.doc(cls)
            if not doc:
                continue

            # split on yaml and new lines
            split_doc = [x.split('\n\n') for x in doc.split('yaml')]
            for item in itertools.chain.from_iterable(split_doc):
                if 'policies:\n' in item:
                    policies.append((item, resource_name, cls.type))
                elif 'resource:' in item:
                    item = 'policies:\n' + item
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
        try:
            data = yaml_load(ptext)
        except Exception:
            print('failed %s %s\n %s' % (resource_name, el_name, ptext))
            raise

        for p in data.get('policies', []):
            if p['name'] in policies:
                if policies[p['name']] != p:
                    print('duplicate %s %s %s' % (
                        resource_name, el_name, p['name']))
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
        raise AssertionError("Duplication doc policy names")

    return policies


@pytest.mark.parametrize("provider_name", ('aws', 'azure', 'gcp', 'k8s'))
def test_doc_examples(provider_name):
    load_resources()
    loader = PolicyLoader(Config.empty())
    provider = clouds.get(provider_name)
    policies = get_doc_policies(provider.resources)

    for p in policies.values():
        loader.load_data({'policies': [p]}, 'memory://')

    for p in policies.values():
        # Note max name size here is 54 if it a lambda policy given
        # our default prefix custodian- to stay under 64 char limit on
        # lambda function names.  This applies to AWS and GCP, and
        # afaict Azure.
        if len(p['name']) >= 54 and 'mode' in p:
            raise ValueError(
                "doc policy exceeds name limit policy:%s" % (p['name']))
