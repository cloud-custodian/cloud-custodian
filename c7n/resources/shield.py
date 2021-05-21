# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError
from botocore.paginate import Paginator

from c7n.actions import BaseAction
from c7n.filters import Filter
from c7n.manager import resources
from c7n.query import QueryResourceManager, RetryPageIterator, TypeInfo
from c7n.utils import local_session, type_schema, get_retry


@resources.register('shield-protection')
class ShieldProtection(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'shield'
        enum_spec = ('list_protections', 'Protections', None)
        id = 'Id'
        name = 'Name'
        arn = False
        config_type = 'AWS::Shield::Protection'


@resources.register('shield-attack')
class ShieldAttack(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'shield'
        enum_spec = ('list_attacks', 'Attacks', None)
        detail_spec = (
            'describe_attack', 'AttackId', 'AttackId', 'Attack')
        name = id = 'AttackId'
        date = 'StartTime'
        filter_name = 'ResourceArns'
        filter_type = 'list'
        arn = False


def get_protections_paginator(client):
    return Paginator(
        client.list_protections,
        {'input_token': 'NextToken', 'output_token': 'NextToken', 'result_key': 'Protections'},
        client.meta.service_model.operation_model('ListProtections'))


def get_type_protections(client, model):
    pager = get_protections_paginator(client)
    pager.PAGE_ITERATOR_CLS = RetryPageIterator
    try:
        protections = pager.paginate().build_full_result().get('Protections', [])
    except client.exceptions.ResourceNotFoundException:
        # shield is not enabled in the account, so all resources are not protected
        return []
    return [p for p in protections if model.arn_type in p['ResourceArn']]


ShieldRetry = get_retry(('ThrottlingException',))


class IsShieldProtected(Filter):

    permissions = ('shield:ListProtections',)
    schema = type_schema('shield-enabled', state={'type': 'boolean'})

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client(
            'shield', region_name='us-east-1')

        protections = get_type_protections(client, self.manager.get_model())
        protected_resources = {p['ResourceArn'] for p in protections}

        state = self.data.get('state', False)
        results = []

        for arn, r in zip(self.manager.get_arns(resources), resources):
            r['c7n:ShieldProtected'] = shielded = arn in protected_resources
            if shielded and state:
                results.append(r)
            elif not shielded and not state:
                results.append(r)
        return results


class SetShieldProtection(BaseAction):
    """Enable shield protection on applicable resource.

    setting `sync` parameter will also clear out stale shield protections
    for resources that no longer exist.
    """

    permissions = ('shield:CreateProtection', 'shield:ListProtections',)
    schema = type_schema(
        'set-shield',
        state={'type': 'boolean'}, sync={'type': 'boolean'})

    def process(self, resources):
        client = local_session(self.manager.session_factory).client(
            'shield', region_name='us-east-1')
        model = self.manager.get_model()
        protections = get_type_protections(client, self.manager.get_model())
        protected_resources = {p['ResourceArn']: p for p in protections}
        state = self.data.get('state', True)

        if self.data.get('sync', False):
            self.clear_stale(client, protections)

        for arn, r in zip(self.manager.get_arns(resources), resources):
            if state and arn in protected_resources:
                continue
            if state is False and arn in protected_resources:
                ShieldRetry(
                    client.delete_protection,
                    ProtectionId=protected_resources[arn]['Id'])
                continue
            try:
                ShieldRetry(
                    client.create_protection,
                    Name=r[model.name], ResourceArn=arn)
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceAlreadyExistsException':
                    continue
                raise

    def clear_stale(self, client, protections):
        # Get all resources unfiltered
        resources = self.manager.get_resource_manager(
            self.manager.type).resources()
        resource_arns = set(self.manager.get_arns(resources))

        pmap = {}
        # Only process stale resources in region for non global resources.
        global_resource = getattr(self.manager.resource_type, 'global_resource', False)
        for p in protections:
            if not global_resource and self.manager.region not in p['ResourceArn']:
                continue
            pmap[p['ResourceArn']] = p

        # Find any protections for resources that don't exist
        stale = set(pmap).difference(resource_arns)
        self.log.info("clearing %d stale protections", len(stale))
        for s in stale:
            ShieldRetry(
                client.delete_protection, ProtectionId=pmap[s]['Id'])
