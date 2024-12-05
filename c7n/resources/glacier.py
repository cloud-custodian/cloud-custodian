# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

import json

from c7n.actions import RemovePolicyBase
from c7n.filters import CrossAccountAccessFilter
from c7n.query import QueryResourceManager, TypeInfo
from c7n.manager import resources
from c7n.utils import get_retry, local_session, type_schema


@resources.register('glacier')
class Glacier(QueryResourceManager):

    permissions = ('glacier:ListTagsForVault',)
    retry = staticmethod(get_retry(('Throttled',)))

    class resource_type(TypeInfo):
        service = 'glacier'
        enum_spec = ('list_vaults', 'VaultList', None)
        name = id = "VaultName"
        arn = "VaultARN"
        arn_type = 'vaults'
        universal_taggable = True

    def augment(self, resources):
        def process_tags(resource):
            client = local_session(self.session_factory).client('glacier')
            tag_dict = self.retry(
                client.list_tags_for_vault,
                vaultName=resource[self.get_model().name])['Tags']
            tag_list = []
            for k, v in tag_dict.items():
                tag_list.append({'Key': k, 'Value': v})
            resource['Tags'] = tag_list
            return resource

        with self.executor_factory(max_workers=2) as w:
            return list(w.map(process_tags, resources))


@Glacier.filter_registry.register('cross-account')
class GlacierCrossAccountAccessFilter(CrossAccountAccessFilter):
    """Filter to return all glacier vaults with cross account access permissions

    The whitelist parameter will omit the accounts that match from the return

    :example:

        .. code-block:

            policies:
              - name: check-glacier-cross-account
                resource: glacier
                filters:
                  - type: cross-account
                    whitelist:
                      - permitted-account-01
                      - permitted-account-02
    """
    permissions = ('glacier:GetVaultAccessPolicy',)

    def process(self, resources, event=None):
        def _augment(r):
            client = local_session(
                self.manager.session_factory).client('glacier')
            try:
                r['Policy'] = client.get_vault_access_policy(
                    vaultName=r['VaultName'])['policy']['Policy']
                return r
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDeniedException':
                    self.log.warning(
                        "Access denied getting policy glacier:%s",
                        r['FunctionName'])

        self.log.debug("fetching policy for %d glacier" % len(resources))
        with self.executor_factory(max_workers=3) as w:
            resources = list(filter(None, w.map(_augment, resources)))

        return super(GlacierCrossAccountAccessFilter, self).process(
            resources, event)


@Glacier.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """Action to remove policy statements from Glacier

    :example:

    .. code-block:: yaml

            policies:
              - name: glacier-cross-account
                resource: glacier
                filters:
                  - type: cross-account
                actions:
                  - type: remove-statements
                    statement_ids: matched
    """

    permissions = ('glacier:SetVaultAccessPolicy', 'glacier:GetVaultAccessPolicy')

    def process(self, resources):
        results = []
        client = local_session(self.manager.session_factory).client('glacier')
        for r in resources:
            try:
                results += filter(None, [self.process_resource(client, r)])
            except Exception:
                self.log.exception(
                    "Error processing glacier:%s", r['VaultARN'])
        return results

    def process_resource(self, client, resource):
        if 'Policy' not in resource:
            try:
                resource['Policy'] = client.get_vault_access_policy(
                    vaultName=resource['VaultName'])['policy']['Policy']
            except ClientError as e:
                if e.response['Error']['Code'] != "ResourceNotFoundException":
                    raise
                resource['Policy'] = None

        if not resource['Policy']:
            return

        p = json.loads(resource['Policy'])
        statements, found = self.process_policy(
            p, resource, CrossAccountAccessFilter.annotation_key)

        if not found:
            return

        if not statements:
            client.delete_vault_access_policy(
                vaultName=resource['VaultName'])
        else:
            client.set_vault_access_policy(
                vaultName=resource['VaultName'],
                policy={'Policy': json.dumps(p)}
            )
        return {'Name': resource['VaultName'],
                'State': 'PolicyRemoved',
                'Statements': found}


@Glacier.action_registry.register('delete')
class GlacierVaultDelete(RemovePolicyBase):
    """Action to delete glacier vaults

    :example:

    .. code-block:: yaml

            policies:
              - name: glacier-vault-delete
                resource: aws.glacier
                filters:
                  - type: cross-account
                actions:
                  - type: delete
    """

    schema = type_schema('delete')
    permissions = ('glacier:DeleteVault',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('glacier')
        for r in resources:
            self.manager.retry(client.delete_vault, vaultName=r['VaultName'], ignore_err_codes=(
                'ResourceNotFoundException',))
