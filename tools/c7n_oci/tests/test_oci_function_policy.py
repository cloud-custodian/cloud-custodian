# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os

import pytest
from oci_common import OciBaseTest

from c7n.exceptions import PolicyValidationError


class TestOciFunctionPolicy(OciBaseTest):
    def test_resource_not_supported(self, test):
        with pytest.raises(PolicyValidationError) as error:
            test.load_policy(
                {
                    "name": "test-update-function-event-mode",
                    "resource": "oci.zone",
                    "mode": {
                        "type": "oci-event",
                        "subnets": ["ocid1.subnet.oc1..<unique_ID>"],
                        "events": ["create"],
                    },
                    "actions": [
                        {"type": "update", "freeform_tags": {"Source": "Custodian-function"}}
                    ],
                }
            )

        assert str(error.value) == "Resource:oci.zone is not supported by event mode currently"

    def test_auth_token_is_not_set(self, test, monkeypatch):
        monkeypatch.delenv("OCI_AUTH_TOKEN", raising=False)
        assert os.getenv("OCI_AUTH_TOKEN") is None
        with pytest.raises(PolicyValidationError) as error:
            test.load_policy(
                {
                    "name": "test-update-function-event-mode",
                    "resource": "oci.bucket",
                    "mode": {
                        "type": "oci-event",
                        "subnets": ["ocid1.subnet.oc1..<unique_ID>"],
                        "events": ["createbucket"],
                    },
                    "actions": [
                        {"type": "update", "freeform_tags": {"Source": "Custodian-function"}}
                    ],
                }
            )

        assert (
            str(error.value)
            == "OCI_AUTH_TOKEN enviornment variable is not set or it is empty. \
It is required to log in to Oracle Cloud Infrastructure Registry."
        )
