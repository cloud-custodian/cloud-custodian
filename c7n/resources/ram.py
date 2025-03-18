from c7n.exceptions import PolicyValidationError
from c7n.filters import Filter
from c7n.manager import resources
from c7n.query import DescribeSource, QueryResourceManager, TypeInfo
from c7n.resolver import ValuesFrom
from c7n.utils import get_retry, local_session, type_schema


class RamResourceShareDescribe(DescribeSource):
    def get_resources(self, ids, cache=True):
        resources = super().get_resources(ids, cache)
        self.manager.switch_enum_specs()
        resources.extend(super().get_resources(ids, cache))
        return resources

    def resources(self, query=None):
        resources = super().resources(query)
        self.manager.switch_enum_specs()
        resources.extend(super().resources(query))
        return resources


@resources.register('ram-resource-share')
class RAMResourceShare(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'ram'
        enum_spec = (
            'get_resource_shares', 'resourceShares',
            {"resourceOwner": "SELF", "resourceShareStatus": "ACTIVE"})
        second_enum_spec = (
            'get_resource_shares', 'resourceShares',
            {"resourceOwner": "OTHER-ACCOUNTS", "resourceShareStatus": "ACTIVE"})
        filter_name = 'resourceShareArns'
        filter_type = 'list'
        arn = id = 'resourceShareArn'
        name = 'name'
        cfn_type = 'AWS::RAM::ResourceShare'
        date = 'lastUpdatedTime'
        universal_taggable = object()

    retry = staticmethod(get_retry(
        ('ServerInternalException', 'ServiceUnavailableException',
         'ThrottlingException',)))

    source_mapping = {
        'describe': RamResourceShareDescribe
    }

    def switch_enum_specs(self):
        self.resource_type.enum_spec = self.resource_type.second_enum_spec


@RAMResourceShare.action_registry.register('external-share')
class ExternalShareFilter(Filter):
    """Check a Resource Share's associations for non-whitelisted entities

    :example:

    .. code-block:: yaml

        policies:
          - name: ram-external-share
            resource: ram-resource-share
            filters:
              - type: external-share
                whitelist_accounts:
                  - "123456789012"
                whitelist_accounts_from:
                    expr: keys(not_null(accounts, `[]`))
                    url: s3://my-bucket/my-aws-accounts.json
    """

    schema = type_schema(
        'external-share',
        whitelist_accounts={'type': 'array', 'items': {'type': 'string'}},
        whitelist_accounts_from={'$ref': '#/definitions/filters_common/value_from'},
        whitelist_orgids={'type': 'array', 'items': {'type': 'string'}},
        whitelist_orgids_from={'$ref': '#/definitions/filters_common/value_from'},
        whitelist_org_units={'type': 'array', 'items': {'type': 'string'}},
        whitelist_org_units_from={'$ref': '#/definitions/filters_common/value_from'},
        whitelist_iam_users={'type': 'array', 'items': {'type': 'string'}},
        whitelist_iam_users_from={'$ref': '#/definitions/filters_common/value_from'},
        whitelist_iam_roles={'type': 'array', 'items': {'type': 'string'}},
        whitelist_iam_roles_from={'$ref': '#/definitions/filters_common/value_from'},
        whitelist_service_principals={'type': 'array', 'items': {'type': 'string'}},
        whitelist_service_principals_from={'$ref': '#/definitions/filters_common/value_from'},
    )

    annotation_key = 'c7n:ExternalShareViolations'
    associations_attribute = 'c7n:Associations'

    def get_share_associations(self, r):
        if not r.get(self.associations_attribute):
            client = local_session(
                self.manager.session_factory
            ).client(self.manager.resource_type.service)
            assocs = self.manager.retry(
                client.get_resource_share_associations,
                associationType='PRINCIPAL',
                resourceShareArn=r['resourceShareArn']
            )["resourceShareAssociations"]
            r[self.associations_attribute] = assocs

    def process(self, resources, event=None):
        results = []
        for r in resources:
            allowed_entities = set(self.manager.config.account_id)
            for whitelist in [
                p for p in self.schema["properties"]
                if p.startswith("whitelist") and not p.endswith("from")
            ]:
                allowed_entities = allowed_entities.union(self.data.get(whitelist, ()))
                if f"{whitelist}_from" in self.data:
                    values = ValuesFrom(self.data[f"{whitelist}_from"], self.manager)
                    allowed_entities = allowed_entities.union(values.get_values())

            if r['owningAccountId'] not in allowed_entities:
                # no need to check associated entities if owning account isn't whitelisted
                violations = [r['owningAccountId']]
            else:
                self.get_share_associations(r)
                share_entities = {r['associatedEntity'] for r in r[self.associations_attribute]}
                violations = share_entities.difference(allowed_entities)

            if violations:
                r[self.annotation_key] = violations
                results.append(r)
        return results


@RAMResourceShare.action_registry.register('disassociate')
class DisassociateResourceShare(Filter):
    """Action to disassociate principals from a Resource Share
    https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ram/client/disassociate_resource_share.html
    :example:

    .. code-block:: yaml

        policies:
            - name: disassociate-ram-resource-share
                resource: ram-resource-share
                filters:
                - type: external-share
                    whitelist_accounts:
                    - 123456789012
                    whitelist_orgids:
                    - o-abcd1234
                actions:
                - disassociate
                  principals: matched
    """

    schema = type_schema(
        'disassociate',
        required={'oneOf': ['principals', 'resource_arns']},
        principals={'oneOf': [
            {'enum': ['matched', 'all']},
            {'type': 'array', 'items': {'type': 'string'}},
        ]},
        resource_arns={'type': 'array', 'items': {'type': 'string'}},
    )
    permissions = ('ram:DisassociateResourceShare',)

    def validate(self):
        if self.data.get('principals') == 'matched':
            ftypes = {f.type for f in self.manager.iter_filters()}
            if 'external-share' not in ftypes:
                raise PolicyValidationError(
                    "external-share filter is required when principals is 'matched'"
                )
        return self

    def process(self, resources):
        _all = self.data.get('principals') == 'all'
        matched = self.data.get('principals') == 'matched'
        resource_arns = self.data.get('resource_arns', [])
        principals = self.data.get('principals', [])

        client = local_session(
            self.manager.session_factory
        ).client(self.manager.resource_type.service)

        for r in resources:
            if resource_arns:
                self.manager.retry(
                    client.disassociate_resource_share,
                    resourceShareArn=r['resourceShareArn'],
                    resourceArns=resource_arns
                )

            if principals:
                if _all:
                    if ExternalShareFilter.associations_attribute not in resources[0]:
                        assocs = self.manager.retry(
                            client.get_resource_share_associations,
                            associationType='PRINCIPAL',
                            resourceShareArn=r['resourceShareArn']
                        )['resourceShareAssociations']

                    principals = [a['associatedEntity'] for a in assocs]
                elif matched:
                    principals = r[ExternalShareFilter.annotation_key]

                self.manager.retry(
                    client.disassociate_resource_share,
                    resourceShareArn=r['resourceShareArn'],
                    principals=principals
                )


@RAMResourceShare.action_registry.register('delete')
class DeleteResourceShare(Filter):
    """Action to delete a Resource Share

    :example:

    .. code-block:: yaml

        policies:
            - name: delete-ram-resource-share
            resource: ram-resource-share
            filters:
            - type: external-share
              whitelist_accounts:
                - 123456789012
              whitelist_orgids:
                - o-abcd1234
            actions:
                - delete
    """

    schema = type_schema('delete')
    permissions = ('ram:DeleteResourceShare',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory
        ).client(self.manager.resource_type.service)
        for r in resources:
            self.manager.retry(client.delete_resource_share, resourceShareArn=r['resourceShareArn'])
