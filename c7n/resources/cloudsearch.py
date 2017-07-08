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

from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema


@resources.register('cloudsearch')
class CloudSearch(QueryResourceManager):

    class resource_type(object):
        service = "cloudsearch"
        enum_spec = ("describe_domains", "DomainStatusList", None)
        name = id = "DomainName"
        dimension = "DomainName"


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
