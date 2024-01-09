# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from typing import List

from c7n.actions import BaseAction
from c7n.filters import CrossAccountAccessFilter, Filter, FilterRegistry
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.manager import resources
from c7n.exceptions import PolicyValidationError
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema

pp_filters = FilterRegistry('catalog-provisioned-product.filters')

class DescribePortfolio(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('catalog-portfolio')
class CatalogPortfolio(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'servicecatalog'
        enum_spec = ('list_portfolios', 'PortfolioDetails', None)
        detail_spec = ('describe_portfolio', 'Id', 'Id', None)
        arn = 'ARN'
        arn_type = 'portfolio'
        id = 'Id'
        name = 'DisplayName'
        date = 'CreatedTime'
        universal_taggable = object()
        cfn_type = config_type = 'AWS::ServiceCatalog::Portfolio'

    source_mapping = {
        'describe': DescribePortfolio,
        'config': ConfigSource
    }


@CatalogPortfolio.action_registry.register('delete')
class CatalogPortfolioDeleteAction(BaseAction):
    """Action to delete a Service Catalog Portfolio

    :example:

    .. code-block:: yaml

        policies:
          - name: service-catalog-portfolio-delete
            resource: aws.catalog-portfolio
            filters:
              - type: cross-account
            actions:
              - delete
    """

    schema = type_schema('delete')
    permissions = ('servicecatalog:DeletePortfolio',)

    def process(self, portfolios):
        client = local_session(self.manager.session_factory).client('servicecatalog')
        for r in portfolios:
            self.manager.retry(client.delete_portfolio, Id=r['Id'], ignore_err_codes=(
                'ResourceNotFoundException',))


@CatalogPortfolio.filter_registry.register('cross-account')
class CatalogPortfolioCrossAccount(CrossAccountAccessFilter):
    """Check for account ids that the service catalog portfolio is shared with

    :example:

    .. code-block:: yaml

            policies:
              - name: catalog-portfolio-cross-account
                resource: aws.catalog-portfolio
                filters:
                  - type: cross-account
    """

    schema = type_schema(
        'cross-account',
        whitelist_from={'$ref': '#/definitions/filters_common/value_from'},
        whitelist={'type': 'array', 'items': {'type': 'string'}})

    permissions = ('servicecatalog:ListPortfolioAccess',)
    annotation_key = 'c7n:CrossAccountViolations'

    def check_access(self, client, accounts, resources):
        results = []
        for r in resources:
            shared_accounts = self.manager.retry(
                client.list_portfolio_access, PortfolioId=r['Id'], ignore_err_codes=(
                    'ResourceNotFoundException',)).get('AccountIds')
            if not shared_accounts:
                continue
            shared_accounts = set(shared_accounts)
            delta_accounts = shared_accounts.difference(accounts)
            if delta_accounts:
                r[self.annotation_key] = list(delta_accounts)
                results.append(r)
        return results

    def process(self, resources, event=None):
        results = []
        client = local_session(self.manager.session_factory).client('servicecatalog')
        accounts = self.get_accounts()
        results.extend(self.check_access(client, accounts, resources))
        return results


@CatalogPortfolio.action_registry.register('remove-shared-accounts')
class RemoveSharedAccounts(BaseAction):
    """Action to delete Portfolio share with other accounts

    :example:

    .. code-block:: yaml

            policies:
              - name: catalog-portfolio-delete-share
                resource: aws.catalog-portfolio
                filters:
                  - type: cross-account
                actions:
                  - type: remove-shared-accounts
                    accounts: matched

              - name: catalog-portfolio-delete-shared-account
                resource: aws.catalog-portfolio
                filters:
                  - type: cross-account
                actions:
                  - type: remove-shared-accounts
                    accounts: ['123456789123']
    """

    schema = type_schema(
        'remove-shared-accounts',
        accounts={'oneOf': [
            {'enum': ['matched']},
            {'type': 'array', 'items': {'type': 'string', 'pattern': '^[0-9]{12}$'}}]},
        required=['accounts'])

    permissions = ('servicecatalog:DeletePortfolioShare',)

    def validate(self):
        if self.data['accounts'] != 'matched':
            return
        found = False
        for f in self.manager.iter_filters():
            if isinstance(f, CatalogPortfolioCrossAccount):
                found = True
                break
        if not found:
            raise PolicyValidationError(
                "policy:%s action:%s with matched requires cross-account filter" % (
                    self.manager.ctx.policy.name, self.type))

    def delete_shared_accounts(self, client, portfolio):
        accounts = self.data.get('accounts')
        if accounts == 'matched':
            accounts = portfolio.get(CatalogPortfolioCrossAccount.annotation_key)
        for account in accounts:
            client.delete_portfolio_share(PortfolioId=portfolio['Id'], AccountId=account)

    def process(self, portfolios):
        client = local_session(self.manager.session_factory).client('servicecatalog')
        for p in portfolios:
            self.delete_shared_accounts(client, p)


@resources.register('catalog-product')
class CatalogProduct(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'servicecatalog'
        arn_type = 'product'
        enum_spec = ('search_products_as_admin', 'ProductViewDetails[].ProductViewSummary', None)
        detail_spec = ('describe_product_as_admin', 'Id', 'ProductId', None)
        id = 'ProductId'
        name = 'Name'
        arn = 'ProductARN'
        date = 'CreatedTime'
        universal_taggable = object()
        cfn_type = 'AWS::ServiceCatalog::CloudFormationProduct'


@resources.register('catalog-provisioned-product')
class CatalogProvisionedProduct(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'servicecatalog'
        enum_spec = ('search_provisioned_products', 'ProvisionedProducts', None)
        id = 'Id'
        name = 'Name'
        arn = 'Arn'
        arn_type = 'stack'
        date = 'CreatedTime'
        cfn_type = config_type = 'AWS::ServiceCatalog::CloudFormationProvisionedProduct'

    filter_registry = pp_filters


@pp_filters.register('is-deprecated')
class IsDeprecated(Filter):
    """AWS Service Catalog provisioned products with ``DEPRECATED`` guidance

    Filters AWS Service Catalog provisioned products with ``DEPRECATED`` guidance.

    :Example:

    .. code-block:: yaml

        policies:
          - name: provisioned-product-is-deprecated
            resource: catalog-provisioned-product
            filters:
              - type: is-deprecated

    :Example:

    .. code-block:: yaml

        policies:
          - name: provisioned-product-is-NOT-deprecated
            resource: catalog-provisioned-product
            filters:
              - not:
                - type: is-deprecated
    """

    schema = type_schema('is-deprecated')
    permissions = ('servicecatalog:DescribeProvisioningArtifact',)

    def get_permissions(self):
        perms = list(self.permissions)
        perms.extend(self.manager.get_permissions())
        return perms

    def process(self, resources: List[dict], event=None) -> List[dict]:
        client = local_session(
            self.manager.session_factory).client('servicecatalog')
        return [r for r in resources
                if self._is_deprecated(client, r)]

    def _is_deprecated(self, client, provisioned_product: dict) -> bool:
        provisioning_artifact = self.manager.retry(
            client.describe_provisioning_artifact,
            ProductId=provisioned_product['ProductId'],
            ProvisioningArtifactId=provisioned_product['ProvisioningArtifactId'],
        )
        return provisioning_artifact['ProvisioningArtifactDetail']['Guidance'] == 'DEPRECATED'


@pp_filters.register('is-active')
class IsActive(Filter):
    """AWS Service Catalog provisioned products is ``ACTIVE``.

    Filters AWS Service Catalog provisioned products in ``ACTIVE`` status.

    :Example:

    .. code-block:: yaml

        policies:
          - name: provisioned-product-is-active
            resource: catalog-provisioned-product
            filters:
              - type: is-active

    :Example:

    .. code-block:: yaml

        policies:
          - name: provisioned-product-is-NOT-active
            resource: catalog-provisioned-product
            filters:
              - not:
                - type: is-active
    """

    schema = type_schema('is-active')
    permissions = ('servicecatalog:DescribeProvisioningArtifact',)

    def process(self, resources: List[dict], event=None) -> List[dict]:
        client = local_session(
            self.manager.session_factory).client('servicecatalog')
        return [r for r in resources
                if self._is_deprecated(client, r)]

    def _is_deprecated(self, client, provisioned_product: dict) -> bool:
        provisioning_artifact = self.manager.retry(
            client.describe_provisioning_artifact,
            ProvisioningArtifactId=provisioned_product['ProvisioningArtifactId']
        )
        return provisioning_artifact['ProvisioningArtifactDetail']['Active']