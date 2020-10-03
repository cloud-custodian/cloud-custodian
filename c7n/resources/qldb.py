# Copyright 2020 Cloud Custodian Authors
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from c7n.actions import BaseAction as Action
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.manager import resources
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema


class DescribeQLDB(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('qldb')
class QLDB(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'qldb'
        enum_spec = ('list_ledgers', 'Ledgers', None)
        detail_spec = ('describe_ledger', 'Name', 'Name', None)
        arn_type = 'ledger'
        id = name = 'Name'
        date = 'CreationDateTime'
        universal_taggable = object()
        cfn_type = config_type = 'AWS::QLDB::Ledger'
        not_found_err = 'ResourceNotFoundException'

    source_mapping = {
        'describe': DescribeQLDB,
        'config': ConfigSource
    }


@QLDB.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = ('qldb:DeleteLedger', 'qldb:UpdateLedger')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('qldb')
        protected = 0
        for r in resources:
            if r.get('DeletionProtection') and self.data.get('force'):
                try:
                    client.update_ledger(
                        Name=r['Name'],
                        DeletionProtection=False)
                except self.manager.resource_type.not_found_err:
                    continue
            elif r.get('DeletionProtection'):
                protected += 1
                continue
            try:
                client.delete_ledger(Name=r['Name'])
            except self.manager.resource_type.not_found_err:
                continue
        if protected:
            self.log.warning((
                'qldb delete found %d delete-protected resources, '
                'configure force: true to delete'), protected)
