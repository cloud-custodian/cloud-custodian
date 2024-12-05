# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .core import ValueFilter
from .related import RelatedResourceFilter
from c7n.utils import type_schema


class KmsRelatedFilter(RelatedResourceFilter):
    """
    Filter a resource by its associated kms key and optionally the aliasname
    of the kms key by using 'c7n:AliasName'

    :example:

    Match a specific key alias:

        .. code-block:: yaml

            policies:
                - name: dms-encrypt-key-check
                  resource: dms-instance
                  filters:
                    - type: kms-key
                      key: "c7n:AliasName"
                      value: alias/aws/dms

    Or match against native key attributes such as ``KeyManager``, which
    more explicitly distinguishes between ``AWS`` and ``CUSTOMER``-managed
    keys. The above policy can also be written as:

        .. code-block:: yaml

            policies:
                - name: dms-aws-managed-key
                  resource: dms-instance
                  filters:
                    - type: kms-key
                      key: KeyManager
                      value: AWS
    """

    schema = type_schema(
        'kms-key', rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})
    RelatedResource = "c7n.resources.kms.Key"
    AnnotationKey = "matched-kms-key"

    def get_related(self, resources):
        resource_manager = self.get_resource_manager()
        related_ids = self.get_related_ids(resources)
        if len(related_ids) < self.FetchThreshold:
            related = resource_manager.get_resources(list(related_ids))
        else:
            related = resource_manager.resources()
        related_map = {}

        for r in related:
            # `AliasNames` is set when we fetch keys, but only for keys
            # which have aliases defined. Fall back to an empty string
            # to avoid lookup errors in filters.
            r['c7n:AliasName'] = r.get('AliasNames', ('',))[0]
            related_map[r['KeyId']] = r

        return related_map

    def get_related_ids(self, resources):
        related_ids = super().get_related_ids(resources)
        normalized_ids = set()
        for rid in related_ids:
            if rid.startswith('arn:'):  # key arn or alias arn
                if 'alias/' in rid:
                    rid = rid.rsplit(':', 1)[-1]  # alias name
                else:
                    rid = rid.rsplit('/', 1)[-1]  # key id
            if rid.startswith('alias/'):
                rid = self.alias_to_id.get(rid, rid)
            normalized_ids.add(rid)
        return normalized_ids

    def process(self, resources, event=None):
        self.alias_to_id = self.key_alias_to_key_id()
        related = self.get_related(resources)
        return [r for r in resources if self.process_resource(r, related)]

    def key_alias_to_key_id(self):
        # convert key alias to key id for cache lookup
        # else cache lookup returns [] even if the key exists
        key_manager = self.get_resource_manager()
        alias_to_id = {}
        for kid, kaliases in key_manager.alias_map.items():
            alias_to_id.update({alias: kid for alias in kaliases})
        return alias_to_id
