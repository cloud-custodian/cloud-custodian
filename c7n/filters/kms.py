# Copyright 2015-2017 Capital One Services, LLC
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

from botocore.exceptions import ClientError
from .core import ValueFilter
from .related import RelatedResourceFilter
from c7n.utils import local_session, type_schema


class KmsRelatedFilter(RelatedResourceFilter):
    """
    Filter a resource by its associcated kms key and optionally the aliasname
    of the kms key by using 'c7n:AliasName'

    :example:

        .. code-block:: yaml

            policies:
                - name:
                  resource: dms-instance
                  filters:
                    - type: kms-key
                      key: c7n:AliasName
                      value: alias/aws/dms
    """

    schema = type_schema(
        'kms-key', rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})
    RelatedResource = "c7n.resources.kms.Key"
    AnnotationKey = "matched-kms-key"

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('kms')
        related = self.get_related(resources)
        for r in related.values():
            try:
                alias_info = self.manager.retry(client.list_aliases, KeyId=r.get('KeyId'))
            except ClientError as e:
                self.log.warning(e)
                continue
            r['c7n:AliasName'] = alias_info.get('Aliases')[0].get('AliasName', '')
        return [r for r in resources if self.process_resource(r, related)]
