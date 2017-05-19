# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

import functools
import logging
import itertools
from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import (
    chunks, local_session, get_retry, type_schema, generate_arn)

log = logging.getLogger('custodian.es')


@resources.register('elasticsearch')
class ElasticSearchDomain(QueryResourceManager):

    class resource_type(object):
        service = 'es'
        type = "elasticsearch"
        enum_spec = (
            'list_domain_names', 'DomainNames[].DomainName', None)
        id = 'DomainName'
        name = 'Name'
        dimension = "DomainName"

    _generate_arn = _account_id = None
    retry = staticmethod(get_retry(('Throttled',)))

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                'es',
                region=self.config.region,
                account_id=self.config.account_id,
                resource_type='domain',
                separator='/')
        return self._generate_arn

    def get_resources(self, resource_ids):
        client = local_session(self.session_factory).client('es')
        return client.describe_elasticsearch_domains(
            DomainNames=resource_ids)['DomainStatusList']

    def augment(self, domains):
        client = local_session(self.session_factory).client('es')
        model = self.get_model()

        def _augment(resource_set):
            resources = self.retry(
                client.describe_elasticsearch_domains,
                DomainNames=resource_set)['DomainStatusList']
            for r in resources:
                rarn = self.generate_arn(r[model.id])
                r['Tags'] = self.retry(
                    client.list_tags, ARN=rarn).get('TagList', [])
            return resources

        with self.executor_factory(max_workers=1) as w:
            return list(itertools.chain(
                *w.map(_augment, chunks(domains, 5))))


@ElasticSearchDomain.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')
    permissions = ('es:DeleteElastisearchDomain',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('es')
        for r in resources:
            client.delete_elasticsearch_domain(DomainName=r['DomainName'])
