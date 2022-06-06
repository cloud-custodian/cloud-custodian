# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.manager import resources
from c7n.filters import Filter
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema


@resources.register('cloudsearch')
class CloudSearch(QueryResourceManager):
    class resource_type(TypeInfo):
        service = "cloudsearch"
        enum_spec = ("describe_domains", "DomainStatusList", None)
        name = id = "DomainName"
        dimension = "DomainName"
        filter_name = 'DomainNames'
        filter_type = 'list'
        arn_type = "domain"


@CloudSearch.action_registry.register('delete')
class Delete(Action):
    schema = type_schema('delete')
    permissions = ('cloudsearch:DeleteDomain',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('cloudsearch')
        for r in resources:
            if r['Created'] is not True or r['Deleted'] is True:
                continue
            client.delete_domain(DomainName=r['DomainName'])


@CloudSearch.filter_registry.register('domain-options')
class DomainOptionsFilter(Filter):
    """
    Filter for cloud search domains that are domain options not enabled
    :example:

    .. code-block:: yaml

            policies:
              - name: enable-https
                resource: cloudsearch
                filters:
                  - domain-options
    """

    schema = type_schema('domain-options')
    permissions = ('cloudsearch:DescribeDomainEndpointOptions',)

    def process(self, resources, event=None):
        results = []

        client = local_session(self.manager.session_factory).client('cloudsearch')
        for r in resources:
            response = client.describe_domain_endpoint_options(
                DomainName=r['DomainName']
            )
            if not response['DomainEndpointOptions']['Options']['EnforceHTTPS']:
                results.append(r)
        return results


@CloudSearch.action_registry.register('enable-https')
class EnableHttps(Action):
    """Enable HTTPs to cloudsearch

    :example:
    .. code-block:: yaml
            policies:
              - name: enable-https
                resource: cloudsearch
                actions:
                  - type: enable-https
                    tls-security-policy: Policy-Min-TLS-1-0-2019-07


    """

    schema = type_schema('enable-https')
    permissions = ('cloudsearch:UpdateDomainEndpointOptions',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('cloudsearch')
        for r in resources:
            client.update_domain_endpoint_options(
                DomainName=r['DomainName'],
                DomainEndpointOptions={
                    'EnforceHTTPS': True,
                    'TLSSecurityPolicy': self.data.get('tls-security-policy', 'Policy-Min-TLS-1-0-2019-07')
                }
            )

