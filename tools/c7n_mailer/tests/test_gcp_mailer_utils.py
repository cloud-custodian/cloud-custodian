# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import unittest

from c7n_mailer.gcp_mailer.utils import gcp_decrypt, CACHE
from mock import MagicMock


class GcpUtilsTest(unittest.TestCase):
    def test_gcp_decrypt_raw(self):
        self.assertEqual(gcp_decrypt({"test": "value"}, MagicMock(), "test", MagicMock()), "value")

    def test_gcp_decrypt_raw_latest(self):
        mock_client = MagicMock()
        mocked_response = MagicMock()
        mocked_response.payload.data = b"secret value"
        mock_client.access_secret_version.return_value = mocked_response
        self.assertEqual(
            gcp_decrypt({"test": {"secret": "foo"}}, MagicMock(), "test", mock_client),
            "secret value",
        )
        mock_client.access_secret_version.assert_called_with(name="foo/versions/latest")
        self.assertTrue("foo/versions/latest" in CACHE)
        # the value should be cached and we should only see one access secret version call
        value = gcp_decrypt({"test": {"secret": "foo"}}, MagicMock(), "test", mock_client)
        mock_client.access_secret_version.assert_called_once()

        # of course, the value of the secret should not have changed
        self.assertEqual(value, "secret value")
