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
"""AWS Account as a custodian resource.
"""

from datetime import datetime, timedelta

from dateutil.parser import parse as parse_date
from dateutil.tz import tzutc

from c7n.actions import ActionRegistry
from c7n.filters import Filter, FilterRegistry, ValueFilter
from c7n.manager import ResourceManager, resources
from c7n.utils import local_session, get_account_id, type_schema

filters = FilterRegistry('aws.account.actions')
actions = ActionRegistry('aws.account.filters')


@resources.register('account')
class Account(ResourceManager):

    filter_registry = filters
    action_registry = actions

    def resources(self):
        session = local_session(self.session_factory)
        client = session.client('iam')
        return self.filter_resources(
            [{'account_id': get_account_id(session),
              'account_name': client.list_account_aliases(
              ).get('AccountAliases', ('',))[0]}])


@filters.register('check-cloudtrail')
class CloudTrailEnabled(Filter):
    """Is cloud trail enabled for this account, returns
    annotated account resource if trail is not enabled.
    """
    schema = type_schema(
        'check-cloudtrail',
        **{'multi-region': {'type': 'boolean'},
           'global-events': {'type': 'boolean'},
           'running': {'type': 'boolean'},
           'notifies': {'type': 'boolean'},
           'file-digest': {'type': 'boolean'},
           'kms': {'type': 'boolean'},
           'kms-key': {'type': 'string'}})

    def process(self, resources, event=None):
        client = local_session(
            self.manager.session_factory).client('cloudtrail')
        trails = client.describe_trails()['trailList']
        resources[0]['cloudtrails'] = trails
        if self.data.get('global-events'):
            trails = [t for t in trails if t.get('IncludeGlobalServiceEvents')]
        if self.data.get('kms'):
            trails = [t for t in trails if t.get('KmsKeyId')]
        if self.data.get('kms-key'):
            trails = [t for t in trails
                      if t.get('KmsKeyId', '') == self.data['kms-key']]
        if self.data.get('file-digest'):
            trails = [t for t in trails
                      if t.get('LogFileValidationEnabled')]
        if self.data.get('multi-region'):
            trails = [t for t in trails if t.get('IsMultiRegionTrail')]
        if self.data.get('notifies'):
            trails = [t for t in trails if t.get('SNSTopicArn')]
        if self.data.get('running', True):
            running = []
            for t in list(trails):
                t['Status'] = status = client.get_trail_status(
                    Name=t['TrailARN'])
                if status['IsLogging'] and not status.get(
                        'LatestDeliveryError'):
                    running.append(t)
            trails = running
        if trails:
            return []
        return resources


@filters.register('check-config')
class ConfigEnabled(Filter):
    """ Is config service enabled for this account
    """

    schema = type_schema(
        'check-config', **{
            'all-resources': {'type': 'boolean'},
            'running': {'type': 'boolean'},
            'global-resources': {'type': 'boolean'}})

    def process(self, resources, event=None):
        client = local_session(
            self.manager.session_factory).client('config')
        channels = client.describe_delivery_channels()[
            'DeliveryChannels']
        recorders = client.describe_configuration_recorders()[
            'ConfigurationRecorders']
        resources[0]['config_recorders'] = recorders
        resources[0]['config_channels'] = channels
        if self.data.get('global-resources'):
            recorders = [r for r in recorders
                         if r['recordingGroup'].get('includeGlobalResources')]
        if self.data.get('all-resources'):
            recorders = [r for r in recorders
                         if r['recordingGroup'].get('allSupported')]
        if self.data.get('running', True) and recorders:
            status = {s['name']: s for
                      s in client.describe_configuration_recorder_status(
                      )['ConfigurationRecordersStatus']}
            resources[0]['config_status'] = status
            recorders = [r for r in recorders
                         if status[r['name']]['recording']
                         and status[r['name']]['lastStatus'].lower() in (
                             'pending', 'success')]
        if channels and recorders:
            return []
        return resources


@filters.register('iam-summary')
class IAMSummary(ValueFilter):
    """Return annotated account resource if iam summary filter matches.

    Some use cases include, detecting root api keys or mfa usage.

    Example iam summary wrt to matchable fields::

      {
    "UsersQuota": 5000,
            "GroupsPerUserQuota": 10,
            "AttachedPoliciesPerGroupQuota": 10,
            "PoliciesQuota": 1000,
            "GroupsQuota": 100,
            "InstanceProfiles": 0,
            "SigningCertificatesPerUserQuota": 2,
            "PolicySizeQuota": 5120,
            "PolicyVersionsInUseQuota": 10000,
            "RolePolicySizeQuota": 10240,
            "AccountSigningCertificatesPresent": 0,
            "Users": 5,
            "ServerCertificatesQuota": 20,
            "ServerCertificates": 0,
            "AssumeRolePolicySizeQuota": 2048,
            "Groups": 1,
            "MFADevicesInUse": 2,
            "RolesQuota": 250,
            "VersionsPerPolicyQuota": 5,
            "AccountAccessKeysPresent": 0,
            "Roles": 4,
            "AccountMFAEnabled": 1,
            "MFADevices": 3,
            "Policies": 3,
            "GroupPolicySizeQuota": 5120,
            "InstanceProfilesQuota": 100,
            "AccessKeysPerUserQuota": 2,
            "AttachedPoliciesPerRoleQuota": 10,
            "PolicyVersionsInUse": 5,
            "Providers": 0,
            "AttachedPoliciesPerUserQuota": 10,
            "UserPolicySizeQuota": 2048
        }

    """
    schema = type_schema('iam-summary', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        if not resources[0].get('iam_summary'):
            client = local_session(self.manager.session_factory).client('iam')
            resources[0]['iam_summary'] = client.get_account_summary(
                )['SummaryMap']
        if self.match(resources[0]['iam_summary']):
            return resources
        return []


@filters.register('password-policy')
class AccountPasswordPolicy(ValueFilter):
    """Check an account's password policy
    """
    schema = type_schema('password-policy', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        if not resources[0].get('password_policy'):
            client = local_session(self.manager.session_factory).client('iam')
            policy = client.get_account_password_policy().get('PasswordPolicy', {})
            resources[0]['password_policy'] = policy
        if self.match(resources[0]['password_policy']):
            return resources
        return []


@filters.register('service-limit')
class ServiceLimit(Filter):
    """Check if account's service limits are past a given threshold."""

    schema = type_schema(
        'service-limit',
        threshold={'type': 'integer'},
        refresh_period={'type': 'integer'},
        services={'type': 'array', 'items': {
            'enum': ['EC2', 'ELB', 'VPC', 'AutoScaling',
                     'RDS', 'EBS', 'SES', 'IAM']}})

    check_id = 'eW7HH0l7J9'

    check_limit = ('region', 'service', 'limit', 'extant', 'color')

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('support')
        checks = client.describe_trusted_advisor_check_result(
            checkId=self.check_id, language='en')['result']

        resources[0]['ServiceLimits'] = checks
        delta = timedelta(self.data.get('refresh_period', 1))
        check_date = parse_date(checks['timestamp'])
        if datetime.now(tz=tzutc()) - delta > check_date:
            client.refresh_trusted_advisor_check(checkId=self.check_id)
        threshold = self.data.get('threshold')
        exceeded = []
        for resource in checks['flaggedResources']:
            if threshold is None and resource['status'] == 'ok':
                continue
            limit = dict(zip(self.check_limit, resource['metadata']))
            limit['status'] = resource['status']
            limit['region'] = resource['region']
            limit['percentage'] = float(limit['extant']) / float(limit['limit']) * 100
            if threshold and limit['percentage'] < threshold:
                continue
            exceeded.append(limit)
        if exceeded:
            resources[0]['ServiceLimitsExceeded'] = exceeded
            return resources
        return []
