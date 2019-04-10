# Copyright 2018 Capital One Services, LLC
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
Object content classification
"""

from collections import Counter
# import base64
import mimetypes
# import tempfile
# import os

from google.cloud.dlp import DlpServiceClient
from boto3.s3.transfer import TransferConfig


class ObjectContentClassify(object):

    supported_content_types = {
        None: 0,  # "Unspecified"
        'image/jpeg': 1,
        'image/bmp': 2,
        'image/png': 3,
        'image/svg': 4,
        'text/plain': 5,
    }

    def __init__(self, data):
        self.data = data
        self.service = DlpServiceClient()

        limits = {'max_findings_per_request': self.data.get(
            'max-findings-by-item', 10)}
        if 'max-findings-by-item' in self.data:
            limits['max_findings_per_item'] = self.data.get(
                'max-findings-by-type', 10)
        self.inspect_config = {
            'info_types': [{'name': it} for it in self.data['info-types']],
            'include_quote': self.data.get('include-quote', False),
            'min_likelihood': self.data.get(
                'min-likelihood', 'LIKELIHOOD_UNSPECIFIED'),
            'limits': limits,
        },
        self.transfer_config = TransferConfig(use_threads=False)
        self.mime_types = mimetypes.MimeTypes()

    def process_object(self, key, object_download):
        fname = key.rsplit('/', 1)
        mime_guess = self.mime_types.guess_type(fname)
        result = self.service.inspect_content(
            self.project,
            self.inspect_config,
            {'item': {
                'type': self.supported_content_types.get(mime_guess, 0),
                'value': object_download['Body'].read()}})
        if not result.findings:
            return False
        result = {
            'key': key['Key'],
            'findings': dict(Counter([r.info_type for r in result.findings]))}
        return result

    def process_key(self, client, bucket_name, key):
        return self.process_object(
            key, client.get_object(Bucket=bucket_name, Key=key['Key']))

    def process_version(self, client, bucket_name, key):
        return self.process_object(
            key,
            client.get_object_version(
                Bucket=bucket_name,
                Key=key['Key'],
                VersionId=key['VersionId']))
