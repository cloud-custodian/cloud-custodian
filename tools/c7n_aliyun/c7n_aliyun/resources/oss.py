# Copyright 2017-2018 Capital One Services, LLC
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
import logging
import os

import jmespath
import oss2
from oss2.api import logger as apiLogger

from c7n.filters import Filter
from c7n.utils import set_annotation
from c7n.utils import type_schema
from c7n_aliyun.provider import resources
from c7n_aliyun.query import QueryResourceManager, TypeInfo
from c7n_aliyun.filters.filter import AliyunOssFilter

apiLogger.setLevel(logging.ERROR)
service = 'oss'
accessKeyId = os.getenv('ALIYUN_ACCESSKEYID')
accessSecret = os.getenv('ALIYUN_ACCESSSECRET')
regionId = os.getenv('ALIYUN_DEFAULT_REGION')


@resources.register('oss')
class Oss(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'oss'
        enum_spec = (None, 'buckets', None)
        id = 'name'

    def get_request(self):
        return regionId


@Oss.filter_registry.register('global-grants')
class GlobalGrantsFilter(Filter):
    """Filters :example:
    .. code-block:: yaml

       policies:
         # private、public-read、public-read-write
         - name: aliyun-oss-global-grants
           resource: aliyun.oss
           filters:
            - type: global-grants
              value: 'public-read'
    """

    schema = type_schema(
        'global-grants',
        **{'value': {'type': 'string'}},
        allow_website={'type': 'boolean'},
        operator={'type': 'string', 'enum': ['or', 'and']},
        permissions={
            'type': 'array', 'items': {
                'type': 'string', 'enum': [
                    'READ', 'WRITE', 'WRITE_ACP', 'READ_ACP', 'FULL_CONTROL']}})

    def process(self, buckets, event=None):
        with self.executor_factory(max_workers=5) as w:
            results = w.map(self.process_bucket, buckets)
            results = list(filter(None, list(results)))
            return results

    def process_bucket(self, b):
        auth = oss2.Auth(accessKeyId, accessSecret)
        bucket = oss2.Bucket(auth, b['extranet_endpoint'], b['name'])

        # 有效值：private、public-read、public-read-write
        acl = bucket.get_bucket_acl().acl

        if self.data['value'] not in acl:
            return

        results = []
        perms = self.data.get('permissions', [])
        if not perms or (perms and acl in perms):
            results.append(acl)

        if results:
            set_annotation(b, 'GlobalPermissions', results)
            return b


@Oss.filter_registry.register('encryption')
class GlobalGrantsFilter(Filter):
    """Filters :example:
    .. code-block:: yaml

       policies:
         # 查看并确认您的OSS存储桶启用了默认加密
         - name: aliyun-oss-encryption
           resource: aliyun.oss
           filters:
            - type: encryption
    """

    schema = type_schema('encryption')

    def process(self, buckets, event=None):
        with self.executor_factory(max_workers=5) as w:
            results = w.map(self.process_bucket, buckets)
            results = list(filter(None, list(results)))
            return results

    def process_bucket(self, i):
        try:
            auth = oss2.Auth(accessKeyId, accessSecret)
            bucket = oss2.Bucket(auth, i['extranet_endpoint'], i['name'])
            result = bucket.get_bucket_encryption()
            if jmespath.search('ServerSideEncryptionRule.SSEAlgorithm', result) is False:
                return i
        except Exception as err:
            i['ServerSideEncryptionRule'] = {"SSEAlgorithm": "None"}
            return i
        return False


@Oss.filter_registry.register('data-redundancy-type')
class DataRedundancyTypeOssFilter(AliyunOssFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测您账号下的对象存储桶是否启用同城冗余存储，若开启视为“合规”。
            - name: aliyun-oss-data-redundancy-type
              resource: aliyun.oss
              filters:
                - type: data-redundancy-type
                  value: ZRS
    """
    # Bucket的数据容灾类型。
    # 有效值：LRS、ZRS
    # 父节点：BucketInfo.Bucket
    schema = type_schema(
        'data-redundancy-type',
        **{'value': {'type': 'string'}})

    def get_request(self, i):
        try:
            auth = oss2.Auth(accessKeyId, accessSecret)
            bucket = oss2.Bucket(auth, i['extranet_endpoint'], i['name'])
            result = bucket.get_bucket_info()
            if self.data['value'] == result.data_redundancy_type:
                return False
            i['DataRedundancyType'] = result.data_redundancy_type
        except Exception as err:
            i['DataRedundancyType'] = "None"
            return i
        return i


@Oss.filter_registry.register('bucket-referer')
class BucketRefererOssFilter(AliyunOssFilter):
    """Filters
       :Example:
       .. code-block:: yaml

        policies:
            # 检测OSS Bucket是否开启防盗链开关，已开通视为合规。
            - name: aliyun-oss-bucket-referer
              resource: aliyun.oss
              filters:
                - type: bucket-referer
                  value: true
    """
    schema = type_schema(
        'bucket-referer',
        **{'value': {'type': 'boolean'}})

    def get_request(self, i):
        try:
            auth = oss2.Auth(accessKeyId, accessSecret)
            bucket = oss2.Bucket(auth, i.get('extranet_endpoint', ''), i.get('name', ''))
            result = bucket.get_bucket_referer()
            if self.data['value']:
                if result.referers:
                    return False
            else:
                return False
            i['BucketReferer'] = result.referers
        except Exception as err:
            i['BucketReferer'] = "None"
            return i
        return i
