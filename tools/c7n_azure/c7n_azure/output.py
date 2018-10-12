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
"""
Provides output support for Azure Blob Storage using
the 'azure://' prefix

"""
import datetime
import logging
import os
import shutil
import tempfile

from c7n_azure.storage_utils import StorageUtilities

from c7n.utils import local_session
from c7n.output import DirectoryOutput, blob_outputs


@blob_outputs.register('azure')
class AzureStorageOutput(DirectoryOutput):
    """
    Usage:

    .. code-block:: python

       with AzureStorageOutput(session_factory, 'azure://bucket/prefix'):
           log.info('xyz')  # -> log messages sent to custodian-run.log.gz

    """

    def __init__(self, ctx, config=None):
        super(AzureStorageOutput, self).__init__(ctx, config)
        self.log = logging.getLogger('custodian.output')

        # folder structure Year/Month/Day/Hour/Second
        self.date_path = datetime.datetime.now().strftime('%Y/%m/%d/%H/%M/%S')
        self.root_dir = tempfile.mkdtemp()
        self.blob_service, self.container, self.file_prefix = \
            self.get_blob_client_wrapper(self.ctx.options.output_dir, ctx)

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        if exc_type is not None:
            self.log.exception("Error while executing policy")
        self.log.debug("Uploading policy logs")
        self.compress()
        self.upload()
        shutil.rmtree(self.root_dir)
        self.log.debug("Policy Logs uploaded")

    def upload(self):
        for root, dirs, files in os.walk(self.root_dir):
            for f in files:
                blob_name = "%s/%s%s" % (
                    self.file_prefix,
                    self.date_path,
                    "%s/%s" % (
                        root[len(self.root_dir):], f))
                blob_name = blob_name.strip('/')
                self.blob_service.create_blob_from_path(
                    self.container,
                    blob_name,
                    os.path.join(root, f))

                self.log.debug("%s uploaded" % blob_name)

    @staticmethod
    def get_blob_client_wrapper(output_path, ctx):
        # provides easier test isolation
        s = local_session(ctx.session_factory)
        return StorageUtilities.get_blob_client_by_uri(output_path, s)
