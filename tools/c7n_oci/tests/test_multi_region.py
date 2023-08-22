# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import inspect
from c7n import policy
from c7n.config import Config
from c7n_oci.provider import OCI
from oci_common import OciBaseTest
from c7n_oci.resources.object_storage import Bucket  # noqa


class TestPolicyCollection(OciBaseTest):
    def _get_default_config(self, regions):
        return Config.empty(regions=regions, region=None, profile=None, account_id=None)

    def _get_policy_data(self):
        data = {"name": "filter-bucket", "resource": "oci.bucket"}
        return {"policies": [data]}

    def test_multi_region(self, test):
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        provider = OCI()
        options = provider.initialize(
            options=self._get_default_config(["us-ashburn-1", "us-phoenix-1"])
        )
        original = policy.PolicyCollection.from_data(
            data=self._get_policy_data(),
            options=options,
            session_factory=session_factory,
        )
        collection = provider.initialize_policies(original, options=options)
        assert len(collection.policies) == 2

    def test_all_region(self, test):
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        provider = OCI()
        options = provider.initialize(options=self._get_default_config(["all"]))
        original = policy.PolicyCollection.from_data(
            data=self._get_policy_data(),
            options=options,
            session_factory=session_factory,
        )
        collection = provider.initialize_policies(original, options=options)
        assert len(collection.policies) == 4

    def test_invalid_region(self, test):
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        provider = OCI()
        options = provider.initialize(
            options=self._get_default_config(["us-ashburn-1", "us-invalid-1"])
        )
        original = policy.PolicyCollection.from_data(
            data=self._get_policy_data(),
            options=options,
            session_factory=session_factory,
        )
        collection = provider.initialize_policies(original, options=options)
        assert len(collection.policies) == 1
