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
from botocore.exceptions import ClientError

from c7n.filters import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session


@resources.register('ecr')
class ECR(QueryResourceManager):

    class Meta(object):
        service = 'ecr'
        enum_spec = ('describe_repositories', 'repositories', None)
        name = "repositoryName"
        id = "repositoryArn"
        dimension = None

    resource_type = Meta


@ECR.filter_registry.register('cross-account')
class ECRCrossAccountAccessFilter(CrossAccountAccessFilter):

    def process(self, resources, event=None):

        def _augment(r):
            client = local_session(self.manager.session_factory).client('ecr')
            try:
                r['Policy'] = client.get_repository_policy(
                    repositoryName=r['repositoryName'])['policyText']
            except ClientError as e:
                if e.response['Error']['Code'] == 'RepositoryPolicyNotFoundException':
                    return None
                raise
            return r

        self.log.debug("fetching policy for %d repos" % len(resources))
        with self.executor_factory(max_workers=3) as w:
            resources = filter(None, w.map(_augment, resources))

        return super(ECRCrossAccountAccessFilter, self).process(resources, event)
