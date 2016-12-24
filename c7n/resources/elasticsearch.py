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
import itertools
from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import chunks, local_session, type_schema


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
        filter_name = None

    def augment(self, resources):

        def _augment(resource_set):
            client = local_session(self.session_factory).client('es')
            return client.describe_elasticsearch_domains(
                DomainNames=resource_set)['DomainStatusList']

        with self.executor_factory(max_workers=2) as w:
            return list(itertools.chain(
                *w.map(_augment, chunks(resources, 20))))

    def get_resources(self, resource_ids):
        client = local_session(self.session_factory).client('es')
        return client.describe_elasticsearch_domains(
            DomainNames=resource_ids)['DomainStatusList']


@ElasticSearchDomain.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('es')
        for r in resources:
            client.delete_elasticsearch_domain(DomainName=r['DomainName'])
