# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n import query
from c7n.utils import local_session, type_schema
from c7n.tags import Tag, RemoveTag
from c7n.actions import BaseAction


class PmtcryptAppJobDescribe(query.DescribeSource):
    def augment(self, pmt_crypt_keys):
        client = local_session(self.manager.session_factory).client('payment-cryptography')
        for r in pmt_crypt_keys:
            tags = client.list_tags_for_resource(ResourceArn=r["KeyArn"]).get('Tags', [])
            r['Tags'] = tags
        return pmt_crypt_keys


@resources.register('payment-cryptography')
class PmtcryptApp(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'payment-cryptography'
        enum_spec = ('list_keys', 'Keys[]', {'KeyState': 'CREATE_COMPLETE'})
        cfn_type = "AWS::PaymentCryptography::Key"
        arn = id = name = "KeyArn"
        permission_prefix = 'payment-cryptography'
        detail_spec = (
            'get_key', 'KeyIdentifier',
            'KeyArn', 'Key')

    source_mapping = {"describe": PmtcryptAppJobDescribe, }


@PmtcryptApp.action_registry.register('tag')
class PmtcryptTag(Tag):
    """Action to tag a payment-cryptography-key"""

    batch_size = 1
    permissions = ('payment-cryptography:TagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            self.manager.retry(client.tag_resource, ResourceArn=r["KeyArn"], Tags=tags)


@PmtcryptApp.action_registry.register('remove-tag')
class PmtcryptRemoveTag(RemoveTag):
    """Action to remove tag(s) from a payment-cryptography-key"""

    batch_size = 1
    permissions = ('payment-cryptography:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            self.manager.retry(
                client.untag_resource, ResourceArn=r["KeyArn"], TagKeys=tags)


@PmtcryptApp.action_registry.register('delete')
class PmtcryptDelete(BaseAction):
    """Action to delete a payment-cryptography-key
    :example

    .. code-block:: yaml

            policies:
                - name: payment-crpytography-delete
                  resource: payment-cryptography
                  filters:
                    - "tag:custodian_cleanup": present
                  actions:
                    - delete
    """

    batch_size = 1
    schema = type_schema('delete')
    permissions = ('payment-cryptography:DeleteKey',)

    def process(self, resource):
        client = local_session(self.manager.session_factory).client('payment-cryptography')
        for r in resource:
            self.manager.retry(
                client.delete_key, KeyIdentifier=r["KeyArn"])
