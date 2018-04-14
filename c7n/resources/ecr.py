# Copyright 2016-2017 Capital One Services, LLC
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

from botocore.exceptions import ClientError

import json
from c7n.filters import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.actions import RemovePolicyBase
from c7n.utils import local_session


@resources.register('ecr')
class ECR(QueryResourceManager):

    class resource_type(object):
        service = 'ecr'
        enum_spec = ('describe_repositories', 'repositories', None)
        name = "repositoryName"
        id = "repositoryArn"
        dimension = None
        filter_name = 'repositoryNames'
        filter_type = 'list'


ErrPolicyNotFound = 'RepositoryPolicyNotFoundException'


@ECR.filter_registry.register('cross-account')
class ECRCrossAccountAccessFilter(CrossAccountAccessFilter):
    """Filters all EC2 Container Registries (ECR) with cross-account access

    :example:

    .. code-block:: yaml

            policies:
              - name: ecr-cross-account
                resource: ecr
                filters:
                  - type: cross-account
                    whitelist_from:
                      expr: "accounts.*.accountNumber"
                      url: *accounts_url
    """
    permissions = ('ecr:GetRepositoryPolicy',)

    def process(self, resources, event=None):

        def _augment(r):
            client = local_session(self.manager.session_factory).client('ecr')
            try:
                r['Policy'] = client.get_repository_policy(
                    repositoryName=r['repositoryName'])['policyText']
            except ClientError as e:
                if e.response['Error']['Code'] == ErrPolicyNotFound:
                    return None
                raise
            return r

        self.log.debug("fetching policy for %d repos" % len(resources))
        with self.executor_factory(max_workers=3) as w:
            resources = list(filter(None, w.map(_augment, resources)))

        return super(ECRCrossAccountAccessFilter, self).process(
            resources, event)


@ECR.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """Action to remove policy statements from ECR

    :example:

    .. code-block:: yaml

            policies:
              - name: ecr-remove-cross-accounts
                resource: ecr
                filters:
                  - type: cross-account
                actions:
                  - type: remove-statements
                    statement_ids: matched
    """

    permissions = ("ecr:SetRepositoryPolicy", "ecr:GetRepositoryPolicy")

    def process(self, resources):
        results = []
        client = local_session(self.manager.session_factory).client('ecr')
        for r in resources:
            try:
                results += filter(None, [self.process_resource(client, r)])
            except Exception:
                self.log.exception(
                    "Error processing ecr registry:%s", r['repositoryArn'])
        return results

    def process_resource(self, client, resource):
        if 'Policy' not in resource:
            try:
                resource['Policy'] = client.get_repository_policy(
                    repositoryName=resource['repositoryName'])['policyText']
            except ClientError as e:
                if e.response['Error']['Code'] != ErrPolicyNotFound:
                    raise
                resource['Policy'] = None

        if not resource['Policy']:
            return

        p = json.loads(resource['Policy'])
        statements, found = self.process_policy(
            p, resource, CrossAccountAccessFilter.annotation_key)

        if not found:
            return

        if not statements:
            client.delete_repository_policy(
                repositoryName=resource['repositoryName'])
        else:
            client.set_repository_policy(
                repositoryName=resource['repositoryName'],
                policyText=json.dumps(p))
        return {'Name': resource['repositoryName'],
                'State': 'PolicyRemoved',
                'Statements': found}
