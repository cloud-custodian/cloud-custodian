# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os

import pytest
from oci_common import OciBaseTest

from c7n.exceptions import PolicyValidationError
from unittest.mock import Mock, patch, MagicMock


class TestOciFunctionPolicy(OciBaseTest):
    def test_resource_not_supported(self, test):
        mock = Mock()
        with patch('docker.from_env') as mock_from_env:
            mock_docker_client = Mock(spec_set=['version', 'login'])
            mock_from_env.return_value = mock_docker_client
            mock_docker_client.version.return_value = mock
            mock_docker_client.login.return_value = mock
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
        mock = Mock()
        with patch('docker.from_env') as mock_from_env:
            mock_docker_client = Mock(spec_set=['version', 'login'])
            mock_from_env.return_value = mock_docker_client
            mock_docker_client.version.return_value = mock
            mock_docker_client.login.return_value = mock
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

    def test_docker_is_not_running(self, test):
        import docker

        with patch('docker.from_env') as mock_from_env:
            mock_client = MagicMock()
            mock_client.version.side_effect = docker.errors.DockerException(
                'Docker is not installed or not running.'
            )
            mock_from_env.return_value = mock_client

            # Ensure that PolicyValidationError is raised
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
            assert str(error.value) == "Docker is not installed or not running."
