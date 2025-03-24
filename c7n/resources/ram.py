from c7n.actions import Action
from c7n.exceptions import PolicyValidationError
from c7n.filters import Filter
from c7n.manager import resources
from c7n.query import DescribeSource, QueryResourceManager, TypeInfo
from c7n.resolver import ValuesFrom
from c7n.utils import get_retry, local_session, type_schema


class ResourceShareDescribe(DescribeSource):

    def augment(self, resources):
        def _augment(r):
            r['Tags'] = [{'Key': t['key'], 'Value': t['value']} for t in r.get('tags', [])]
            return r
        resources = super().augment(resources)
        return list(map(_augment, resources))


@resources.register('resource-share-other')
class ResourceShareOther(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'ram'
        enum_spec = ('get_resource_shares', 'resourceShares',
                     {"resourceShareStatus": "ACTIVE", "resourceOwner": "OTHER-ACCOUNTS"})
        filter_name = 'resourceShareArns'
        filter_type = 'list'
        arn = id = 'resourceShareArn'
        name = 'name'
        cfn_type = 'AWS::RAM::ResourceShare'
        date = 'lastUpdatedTime'

    retry = staticmethod(get_retry(
        ('ServerInternalException', 'ServiceUnavailableException',
         'ThrottlingException',)))


@resources.register('resource-share-self')
class ResourceShareSelf(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'ram'
        enum_spec = ('get_resource_shares', 'resourceShares',
                     {"resourceShareStatus": "ACTIVE", "resourceOwner": "SELF"})
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
        'describe': ResourceShareDescribe
    }


@ResourceShareSelf.filter_registry.register('external-share')
class ExternalShareFilter(Filter):
    """Check a Resource Share's associations for non-allowlisted entities

    :example:

    .. code-block:: yaml

        policies:
          - name: ram-external-share
            resource: ram-resource-share
            filters:
              - type: external-share
                allowlist_entities:
                  - 123456789012
                  - arn:aws:iam::111111111111:role/MyRole
                  - o-abcd1234
                  - ou-ab12-34cd567890ef
                  - aws:aws:iam::22222222222:user/MyUser
                  - lambda.amazonaws.com
                allowlist_entities_from:
                    expr: keys(not_null(accounts, `[]`))
                    url: s3://my-bucket/my-aws-accounts.json
    """

    schema = type_schema(
        'external-share',
        allowlist_entities={'type': 'array', 'items': {'type': 'string'}},
        allowlist_entities_from={'$ref': '#/definitions/filters_common/value_from'},
    )

    annotation_key = 'c7n:ExternalShareViolations'
    associations_attribute = 'c7n:PrincipalAssociations'
    permissions = ('ram:GetResourceShareAssociations',)

    def get_share_associations(self, resources):
        share_arns = [
            r['resourceShareArn'] for r in resources
            if self.associations_attribute not in r
        ]
        if share_arns:
            client = local_session(
                self.manager.session_factory
            ).client(self.manager.resource_type.service)
            assocs = self.manager.retry(
                client.get_resource_share_associations,
                associationType='PRINCIPAL',
                resourceShareArns=share_arns
            )['resourceShareAssociations']
            associations_map = {}
            # Have to client-side filter by status - (InvalidParameterException) You cannot use
            # ResourceShareArns and AssociationStatus in one request.
            for assoc in [a for a in assocs if a['status'] == 'ASSOCIATED']:
                associations_map.setdefault(assoc['resourceShareArn'], []).append(assoc)
            for r in resources:
                r.setdefault(
                    self.associations_attribute, []
                ).extend(
                    associations_map.get(r['resourceShareArn'], [])
                )
        return resources

    def process(self, resources, event=None):
        results = []
        resources = self.get_share_associations(resources)
        for r in resources:
            allowed_entities = set(self.manager.config.account_id)
            allowed_entities = allowed_entities.union(self.data.get('allowlist_entities', ()))
            if 'allowlist_entities_from' in self.data:
                values = ValuesFrom(self.data['allowlist_entities_from'], self.manager)
                allowed_entities = allowed_entities.union(values.get_values())
            violations = [
                assoc for assoc in r[self.associations_attribute]
                if assoc['associatedEntity'] not in allowed_entities
            ]
            if violations:
                r[self.annotation_key] = violations
                results.append(r)
        return results


@ResourceShareSelf.action_registry.register('disassociate')
class DisassociateResourceShare(Action):
    """Action to disassociate principals from a Resource Share
    https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ram/client/disassociate_resource_share.html
    :example:

    .. code-block:: yaml

        policies:
            - name: disassociate-ram-resource-share
              resource: ram-resource-share-self
              filters:
              - type: external-share
                allowlist_entities:
                  - 123456789012
                  - o-abcd1234
              actions:
              - disassociate
                principals: matched
    """

    schema = type_schema(
        'disassociate',
        required=['principals'],
        principals={'enum': ['matched', 'all']},
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

        client = local_session(
            self.manager.session_factory
        ).client(self.manager.resource_type.service)

        if _all and ExternalShareFilter.associations_attribute not in resources[0]:
            share_arns = [r['resourceShareArn'] for r in resources]
            assocs = self.manager.retry(
                client.get_resource_share_associations,
                associationType='PRINCIPAL',
                resourceShareArns=share_arns
            )['resourceShareAssociations']
            associations_map = {}
            for assoc in [a for a in assocs if a['status'] == 'ASSOCIATED']:
                associations_map.setdefault(assoc['resourceShareArn'], []).append(assoc)
            for r in resources:
                r.setdefault(
                    ExternalShareFilter.associations_attribute, []
                ).extend(
                    associations_map.get(r['resourceShareArn'], [])
                )

        for r in resources:
            if _all:
                principals = [
                    a['associatedEntity']
                    for a in r[ExternalShareFilter.associations_attribute]
                ]
            else:
                principals = [a['associatedEntity'] for a in r[ExternalShareFilter.annotation_key]]

            if principals:
                self.manager.retry(
                    client.disassociate_resource_share,
                    resourceShareArn=r['resourceShareArn'],
                    principals=principals
                )


@ResourceShareSelf.action_registry.register('delete')
class DeleteResourceShare(Action):
    """Action to delete a Resource Share

    :example:

    .. code-block:: yaml

        policies:
            - name: delete-ram-resource-share
            resource: ram-resource-share-self
            filters:
            - type: external-share
              allowlist_entities:
                - 123456789012
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
