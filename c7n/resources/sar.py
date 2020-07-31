# Copyright 2020 Kapil Thangavelu
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


from c7n.actions import Action
from c7n.filters import CrossAccountAccessFilter
from c7n.query import QueryResourceManager, TypeInfo
from c7n.manager import resources
from c7n.utils import type_schema, local_session


@resources.register('serverless-app')
class ServerlessApp(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'serverlessrepo'
        arn = id = 'ApplicationId'
        name = 'Name'
        enum_spec = ('list_applications', 'Applications', None)
        cfn_type = 'AWS::Serverless::Application'
        default_report_fields = [
            'ApplicationId', 'Name', 'CreationTime', 'SpdxLicenseId', 'Author']


@ServerlessApp.action_registry.register('delete')
class Delete(Action):

    permissions = ('serverlessrepo:DeleteApplication',)
    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('serverlessrepo')
        for r in resources:
            self.manager.retry(
                client.delete_application,
                ApplicationId=r['ApplicationId'])


@ServerlessApp.filter_registry.register('cross-account')
class CrossAccount(CrossAccountAccessFilter):

    permissions = ('serverlessrepo:GetApplicationPolicy',)
    policy_attribute = 'c7n:Policy'

    def process(self, resources, event=None):
        client = local_session(
            self.manager.session_factory).client('serverlessrepo')
        for r in resources:
            if self.policy_attribute not in r:
                r[self.policy_attribute] = p = client.get_application_policy(
                    ApplicationId=r['ApplicationId'])
                p.pop('ResponseMetadata', None)
                self.transform_policy(p)
        return super().process(resources)

    def transform_policy(self, policy):
        """Serverless Application repositories policies aren't valid iam policies.

        Its a service specific spelling that violates basic constraints of the iam
        schema. We attempt to normalize it to normal IAM spelling.
        """
        policy['Statement'] = policy.pop('Statements')
        for s in policy['Statement']:
            actions = ['serverlessrepo:%s' % a for a in s['Actions']]
            s['Actions'] = actions
            if 'Effect' not in s:
                s['Effect'] = 'Allow'
            if 'Principals' in s:
                s['Principal'] = {'AWS': s.pop('Principals')}
            if 'PrincipalOrgIDs' in s:
                org_ids = s.pop('PrincipalOrgIDs')
                if org_ids:
                    s['Condition'] = {
                        'StringEquals': {'aws:PrincipalOrgID': org_ids}}
        return policy
