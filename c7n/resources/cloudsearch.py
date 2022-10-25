# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.manager import resources
from c7n.filters import ValueFilter
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
class DomainOptionsFilter(ValueFilter):
    """
    Filter for cloud search domains by their domain options.

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudsearch-detect-https
                resource: cloudsearch
                filters:
                  - type: domain-options
                    key: Options.EnforceHTTPS
                    value: false

    """

    schema = type_schema('domain-options', rinherit=ValueFilter.schema)
    permissions = ('cloudsearch:DescribeDomainEndpointOptions',)

    def process(self, resources, event=None):
        results = []
        client = local_session(self.manager.session_factory).client('cloudsearch')
        for r in resources:
            options = client.describe_domain_endpoint_options(
                DomainName=r['DomainName']
            ).get('DomainEndpointOptions')
            if self.match(options):
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
                filters:
                  - type: domain-options
                    key: Options.EnforceHTTPS
                    value: false
                actions:
                  - type: enable-https
                    tls-policy: Policy-Min-TLS-1-0-2019-07
    """

    schema = type_schema(
        'enable-https',
        **{"tls-policy": {'enum': ['Policy-Min-TLS-1-0-2019-07', 'Policy-Min-TLS-1-2-2019-07']}}
    )
    permissions = ('cloudsearch:UpdateDomainEndpointOptions',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('cloudsearch')
        for r in resources:
            client.update_domain_endpoint_options(
                DomainName=r['DomainName'],
                DomainEndpointOptions={
                    'EnforceHTTPS': True,
                    'TLSSecurityPolicy': self.data.get(
                        'tls-policy', 'Policy-Min-TLS-1-2-2019-07')
                }
            )
