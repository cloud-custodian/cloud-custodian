# Copyright 2015-2018 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

import shutil
import os
import mock

from c7n.ctx import ExecutionContext
from c7n.config import Bag, Config

from azure_common import BaseTest
from c7n_azure.output import AzureStorageOutput


class OutputTest(BaseTest):
    def setUp(self):
        super(OutputTest, self).setUp()

    def get_azure_output(self):
        output = AzureStorageOutput(
            ExecutionContext(
                None,
                Bag(name="xyz"),
                Config.empty(output_dir="azure://mystorage.blob.core.windows.net/logs"),
            )
        )
        self.addCleanup(shutil.rmtree, output.root_dir)

        return output

    def test_azure_output_upload(self):
        # Mock storage utilities to avoid calling azure to get a real client.

        AzureStorageOutput.get_blob_client_wrapper = gm = mock.MagicMock()
        gm.return_value = None, "logs", "xyz"

        output = self.get_azure_output()
        self.assertEqual(output.file_prefix, "xyz")

        # Generate fake output file
        with open(os.path.join(output.root_dir, "foo.txt"), "w") as fh:
            fh.write("abc")

        # Mock the create blob call
        output.blob_service = mock.MagicMock()
        output.blob_service.create_blob_from_path = m = mock.MagicMock()

        output.upload()

        m.assert_called_with(
            "logs",
            "xyz/%s/foo.txt" % output.date_path,
            fh.name
        )
