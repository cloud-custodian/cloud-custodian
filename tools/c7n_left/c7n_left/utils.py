# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#

from c7n.provider import clouds
from c7n.loader import DirectoryLoader


def load_policies(policy_dir, options):

    loader = DirectoryLoader(config=options)
    policies = loader.load_directory(policy_dir)
    providers = {p.provider_name for p in policies}
    assert len(providers), "only a single provider per policy dir"
    provider_name = providers.pop()
    provider = clouds[provider_name]()
    p_options = provider.initialize(options)
    return provider.initialize_policies(policies, p_options)
