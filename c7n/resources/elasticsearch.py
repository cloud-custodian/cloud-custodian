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
import functools
import logging
import itertools
from botocore.exceptions import ClientError
from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import chunks, local_session, get_retry, type_schema, generate_arn, get_account_id

log = logging.getLogger('custodian.es')

@resources.register('elasticsearch')
class ElasticSearchDomain(QueryResourceManager):

    class resource_type(object):
        service = 'es'
        type = "elasticsearch"
        enum_spec = (
            'list_domain_names', 'DomainNames[]', None)
        id = 'DomainName'
        name = 'Name'
        dimension = "DomainName"
        filter_name = "DomainName"
        filter_type = "scaler"

    _generate_arn = _account_id = None
    retry = staticmethod(get_retry(('Throttled',)))

    @property
    def account_id(self):
        if self._account_id is None:
            session = local_session(self.session_factory)
            self._account_id = get_account_id(session)
        return self._account_id

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                'es',
                region=self.config.region,
                account_id=self.account_id,
                resource_type='domain',
                separator='/')
        return self._generate_arn

    def augment(self, domains):
        filter(None, _elasticsearch_tags(
            self.get_model(),
            domains, self.session_factory, self.executor_factory,
            self.generate_arn, self.retry))
        return domains

def _elasticsearch_tags(
        model, domains, session_factory, executor_factory, generator, retry):
    """ Augment Elasticsearch domains with their respective tags
    """

    def process_tags(domain):
        client = local_session(session_factory).client('es')
        arn = generator(domain[model.id])
        tag_list = retry(
            client.list_tags,
            ARN=arn)['TagList']
        domain['Tags'] = tag_list or []
        return domain

    with executor_factory(max_workers=1) as w:
        return list(w.map(process_tags, domains))

@ElasticSearchDomain.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')
    permissions = ('es:DeleteElastisearchDomain',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('es')
        for r in resources:
            client.delete_elasticsearch_domain(DomainName=r['DomainName'])
