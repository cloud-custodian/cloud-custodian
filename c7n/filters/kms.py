# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError
from .core import ValueFilter
from .related import RelatedResourceFilter
from c7n.utils import local_session, type_schema


class KmsRelatedFilter(RelatedResourceFilter):
    """
    Filter a resource by its associated kms key and optionally the aliasname
    of the kms key by using 'c7n:AliasName'

    :example:

        .. code-block:: yaml

            policies:
                - name: dms-encrypt-key-check
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

    def get_related_ids(self, resources):
        related_ids = super().get_related_ids(resources)
        normalized_ids = []
        for rid in related_ids:
            if rid.startswith('arn:'):
                normalized_ids.append(rid.rsplit('/', 1)[-1])
            else:
                normalized_ids.append(rid)
        return normalized_ids

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
