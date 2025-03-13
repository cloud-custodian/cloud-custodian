from c7n.filters import Filter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.resolver import ValuesFrom
from c7n.utils import local_session, type_schema


@resources.register('ram-resource-share')
class RAMResourceShare(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'ram'
        enum_spec = ('get_resource_shares', 'resourceShares', None)
        arn = id = 'resourceShareArn'
        name = 'name'
        cfn_type = 'AWS::RAM::ResourceShare'
        date = 'lastUpdatedTime'
        universal_taggable = object()


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
            assoc = self.manager.retry(
                client.get_resource_share_associations,
                associationType='PRINCIPAL',
                resourceShareArn=r['resourceShareArn']
            )["resourceShareAssociations"]
            r[self.associations_attribute] = assoc

    def process(self, resources, event=None):
        results = []
        for r in resources:
            self.get_share_associations(r)
            allowed_entities = set(self.manager.config.account_id)
            for whitelist in [
                p for p in self.schema["properties"]
                if p.startswith("whitelist") and not p.endswith("from")
            ]:
                allowed_entities = allowed_entities.union(self.data.get(whitelist, ()))
                if f"{whitelist}_from" in self.data:
                    values = ValuesFrom(self.data[f"{whitelist}_from"], self.manager)
                    allowed_entities = allowed_entities.union(values.get_values())

            share_entities = {r['associatedEntity'] for r in r[self.associations_attribute]}
            violations = share_entities.difference(allowed_entities)
            if violations:
                r[self.annotation_key] = violations
                results.append(r)
        return results
