# Copyright 2017 Capital One Services, LLC
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

from .core import Filter


class FilterKmsInvalid(Filter):
    """Filters out invalid KmsKeyIds
    """
    def process(self, resources, event=None):
        if not self.data.get('value', True):
            return resources
        # try using cache first to get a listing of all KMS Keys and compares resources to the list
        # This will populate the cache.
        kms_keys = self.manager.get_resource_manager('kms-key').resources()
        key_ids = [key['KeyArn'] for key in kms_keys]

        matches = []
        for item in resources:
            if item['Encrypted'] and item['KmsKeyId'] not in key_ids:
                matches.append(item)
        return matches
