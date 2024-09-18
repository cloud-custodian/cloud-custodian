# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import os

from c7n.loader import DirectoryLoader
from c7n.policy import PolicyCollection, Policy
from c7n.provider import clouds


def load_policies(policy_dir, options):
    loader = DirectoryLoader(config=options)
    loader.collection_class = LeftCollection
    policies = loader.load_directory(policy_dir, recurse=False)
    if not policies:
        return ()

    providers = {p.provider_name for p in policies}
    assert len(providers) == 1, "only a single provider per policy dir"
    provider_name = providers.pop()
    provider = clouds[provider_name]()
    p_options = provider.initialize(options)
    return provider.initialize_policies(policies, p_options)


class LeftCollection(PolicyCollection):
    @classmethod
    def from_data(cls, data: dict, options, session_factory=None):
        # session factory param introduction needs an audit and review
        # on tests.
        sf = session_factory if session_factory else cls.session_factory()
        policies = [LeftPolicy(p, options, session_factory=sf) for p in data.get("policies", ())]
        return cls(policies, options)


class LeftPolicy(Policy):
    def get_variables(self, variables=None):
        vars = super().get_variables(variables)
        vars["env"] = dict(os.environ)
        return vars
