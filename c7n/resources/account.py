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


def get_account(session_factory):
    session = local_session(session_factory)
    client = session.client('iam')
    aliases = client.list_account_aliases().get(
        'AccountAliases', ('',))
    name = aliases and aliases[0] or ""
    return {'account_id': get_account_id(session),
            'account_name': name}


@resources.register('account')
class Account(ResourceManager):

    filter_registry = filters
    action_registry = actions

    class resource_type(object):
        id = 'account_id'
        name = 'account_name'

    @classmethod
    def get_permissions(cls):
        return ('iam:ListAccountAliases',)

    def get_model(self):
        return self.resource_type

    def resources(self):
        return self.filter_resources([get_account(self.session_factory)])

    def get_resources(self, resource_ids):
        return [get_account(self.session_factory)]


@filters.register('check-cloudtrail')
class CloudTrailEnabled(Filter):
    """Verify cloud trail enabled for this account per specifications.

    Returns an annotated account resource if trail is not enabled.

    :example:

        .. code-block: yaml

            policies:
              - name: account-cloudtrail-enabled
                resource: account
                region: us-east-1
                filters:
                  - type: check-cloudtrail
                    global-events: true
                    multi-region: true
                    running: true
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

    permissions = ('cloudtrail:DescribeTrails', 'cloudtrail:GetTrailStatus')

    def process(self, resources, event=None):
        client = local_session(
            self.manager.session_factory).client('cloudtrail')
        trails = client.describe_trails()['trailList']
        resources[0]['c7n:cloudtrails'] = trails
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
    """Is config service enabled for this account

    :example:

        .. code-block: yaml

            policies:
              - name: account-check-config-services
                resource: account
                region: us-east-1
                filters:
                  - type: check-config
                    all-resources: true
                    global-resources: true
                    running: true
    """

    schema = type_schema(
        'check-config', **{
            'all-resources': {'type': 'boolean'},
            'running': {'type': 'boolean'},
            'global-resources': {'type': 'boolean'}})

    permissions = ('config:DescribeDeliveryChannels',
                   'config:DescribeConfigurationRecorders',
                   'config:DescribeConfigurationRecorderStatus')

    def process(self, resources, event=None):
        client = local_session(
            self.manager.session_factory).client('config')
        channels = client.describe_delivery_channels()[
            'DeliveryChannels']
        recorders = client.describe_configuration_recorders()[
            'ConfigurationRecorders']
        resources[0]['c7n:config_recorders'] = recorders
        resources[0]['c7n:config_channels'] = channels
        if self.data.get('global-resources'):
            recorders = [
                r for r in recorders
                if r['recordingGroup'].get('includeGlobalResourceTypes')]
        if self.data.get('all-resources'):
            recorders = [r for r in recorders
                         if r['recordingGroup'].get('allSupported')]
        if self.data.get('running', True) and recorders:
            status = {s['name']: s for
                      s in client.describe_configuration_recorder_status(
                      )['ConfigurationRecordersStatus']}
            resources[0]['c7n:config_status'] = status
            recorders = [r for r in recorders
                         if status[r['name']]['recording'] and
                         status[r['name']]['lastStatus'].lower() in
                         ('pending', 'success')]
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

    For example to determine if an account has either not been
    enabled with root mfa or has root api keys.

    .. code-block: yaml

      policies:
        - name: root-keys-or-no-mfa
          resource: account
          filters:
            - type: iam-summary
              key: AccountMFAEnabled
              value: true
              op: eq
              value_type: swap
    """
    schema = type_schema('iam-summary', rinherit=ValueFilter.schema)

    permissions = ('iam:GetAccountSummary',)

    def process(self, resources, event=None):
        if not resources[0].get('c7n:iam_summary'):
            client = local_session(
                self.manager.session_factory).client('iam')
            resources[0]['c7n:iam_summary'] = client.get_account_summary(
                )['SummaryMap']
        if self.match(resources[0]['c7n:iam_summary']):
            return resources
        return []


@filters.register('password-policy')
class AccountPasswordPolicy(ValueFilter):
    """Check an account's password policy

    :example:

        .. code-block: yaml

            policies:
              - name: password-policy-check
                resource: account
                region: us-east-1
                filters:
                  - type: password-policy
                    key: MinimumPasswordLength
                    value: 10
                    op: ge
                  - type: password-policy
                    key: RequireSymbols
                    value: true
    """
    schema = type_schema('password-policy', rinherit=ValueFilter.schema)
    permissions = ('iam:GetAccountPasswordPolicy',)

    def process(self, resources, event=None):
        if not resources[0].get('c7n:password_policy'):
            client = local_session(self.manager.session_factory).client('iam')
            password_policy = client.get_account_password_policy()
            policy = password_policy.get('PasswordPolicy', {})
            resources[0]['c7n:password_policy'] = policy
        if self.match(resources[0]['c7n:password_policy']):
            return resources
        return []


@filters.register('service-limit')
class ServiceLimit(Filter):
    """Check if account's service limits are past a given threshold.

    Supported limits are per trusted advisor, which is variable based
    on usage in the account and support level enabled on the account.

      - service: AutoScaling limit: Auto Scaling groups
      - service: AutoScaling limit: Launch configurations
      - service: EBS limit: Active snapshots
      - service: EBS limit: Active volumes
      - service: EBS limit: General Purpose (SSD) volume storage (GiB)
      - service: EBS limit: Magnetic volume storage (GiB)
      - service: EBS limit: Provisioned IOPS
      - service: EBS limit: Provisioned IOPS (SSD) storage (GiB)
      - service: EC2 limit: Elastic IP addresses (EIPs)

      # Note this is extant for each active instance type in the account
      # however the total value is against sum of all instance types.
      # see issue https://github.com/capitalone/cloud-custodian/issues/516

      - service: EC2 limit: On-Demand instances - m3.medium

      - service: EC2 limit: Reserved Instances - purchase limit (monthly)
      - service: ELB limit: Active load balancers
      - service: IAM limit: Groups
      - service: IAM limit: Instance profiles
      - service: IAM limit: Roles
      - service: IAM limit: Server certificates
      - service: IAM limit: Users
      - service: RDS limit: DB instances
      - service: RDS limit: DB parameter groups
      - service: RDS limit: DB security groups
      - service: RDS limit: DB snapshots per user
      - service: RDS limit: Storage quota (GB)
      - service: RDS limit: Internet gateways
      - service: SES limit: Daily sending quota
      - service: VPC limit: VPCs
      - service: VPC limit: VPC Elastic IP addresses (EIPs)

    :example:

        .. code-block: yaml

            policies:
              - name: account-service-limits
                resource: account
                filters:
                  - type: service-limit
                    services:
                      - IAM
                    threshold: 1.0
    """

    schema = type_schema(
        'service-limit',
        threshold={'type': 'number'},
        refresh_period={'type': 'integer'},
        limits={'type': 'array', 'items': {'type': 'string'}},
        services={'type': 'array', 'items': {
            'enum': ['EC2', 'ELB', 'VPC', 'AutoScaling',
                     'RDS', 'EBS', 'SES', 'IAM']}})

    permissions = ('support:DescribeTrustedAdvisorCheckResult',)
    check_id = 'eW7HH0l7J9'
    check_limit = ('region', 'service', 'check', 'limit', 'extant', 'color')

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('support')
        checks = client.describe_trusted_advisor_check_result(
            checkId=self.check_id, language='en')['result']

        resources[0]['c7n:ServiceLimits'] = checks
        delta_days = timedelta(self.data.get('refresh_period', 1))
        check_date = parse_date(checks['timestamp'])
        if datetime.now(tz=tzutc()) - delta_days > check_date:
            client.refresh_trusted_advisor_check(checkId=self.check_id)
        threshold = self.data.get('threshold')

        services = self.data.get('services')
        limits = self.data.get('limits')
        exceeded = []

        for resource in checks['flaggedResources']:
            if threshold is None and resource['status'] == 'ok':
                continue
            limit = dict(zip(self.check_limit, resource['metadata']))
            if services and limit['service'] not in services:
                continue
            if limits and limit['check'] not in limits:
                continue
            limit['status'] = resource['status']
            limit['percentage'] = float(limit['extant'] or 0) / float(
                limit['limit']) * 100
            if threshold and limit['percentage'] < threshold:
                continue
            exceeded.append(limit)
        if exceeded:
            resources[0]['c7n:ServiceLimitsExceeded'] = exceeded
            return resources
        return []


@filters.register('underutilized-ec2-instance')
class UnderutilisedEc2(Filter):
    """
    Trusted Advisor check to see if there exists any EC2 instances that are
    not fully using computational and network resources.

    schema:
    :param: max_cpu: float value which meets the filter condition if the
        average CPU value returned by trusted advisor for a flagged resource
        is less than this value.
    :param: max_network: float value which meets the filter condition if
        the average network IO in megabytes returned by trusted advisor for a
        flagged resource is less than this value.
    :param: min_savings: float value which meets the filter condition if
        the resource value is greater than the filter parameter value entered.
    :param: max_low_utilization_days: integer value, if the returned number of
        low utilization days for a flagged resource is greater than this
        value the filter condition is met.
    :param: instance_types: array of strings, if the trusted advisor returned
        flagged resource instance type is in this list the filter condition
        is met.
    :param: refresh_period: integer value, max days ago before the trusted
        advisor check is re-run, ensures check results are recent enough to be
        relevant.

    :example:

        .. code-block: yaml

            policies:
              - name: underutilized-ec2
                resource: account
                filters:
                  - type: underutilized-ec2-instance
                    savings_threshold: 20.0
                    instance_types:
                      - r3.large
                      - t2.medium
    """

    schema = type_schema(
        'underutilized-ec2-instance',
        max_cpu={'type': 'number'},
        max_network={'type': 'number'},
        min_savings={'type': 'number'},
        max_low_utilization_days={'type': 'integer'},
        instance_types={'type': 'array', 'items': {'type': 'string'}},
        refresh_period={'type': 'integer'}
    )

    permissions = ('support:DescribeTrustedAdvisorCheckResult',)
    check_id = 'Qch7DwouX1'

    metadata_fields = ('availability zone', 'id', 'name', 'instance type',
                       'estimated monthly savings', 'day 1', 'day 2', 'day 3',
                       'day 4', 'day 5', 'day 6', 'day 7', 'day 8', 'day 9',
                       'day 10', 'day 11', 'day 12', 'day 13', 'day 14',
                       'average CPU', 'average network io',
                       'low utilization days')

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('support')
        checks = client.describe_trusted_advisor_check_result(
            checkId=self.check_id, language='en'
        )['result']

        delta_days = timedelta(self.data.get('refresh_period', 1))
        check_date = parse_date(checks['timestamp'])
        if datetime.now(tz=tzutc()) - delta_days > check_date:
            client.refresh_trusted_advisor_check(checkId=self.check_id)

        # query filter parameters
        filter_params = {
            'max_cpu': self.data.get('max_cpu'),
            'max_network': self.data.get('max_network'),
            'max_low_use_days': self.data.get('max_low_utilization_days'),
            'min_savings': self.data.get('min_savings'),
            'instance_types': self.data.get('instance_types'),
        }

        exceeded = []
        for resource in checks['flaggedResources']:
            resource_data = dict(zip(self.metadata_fields,
                                     resource['metadata']))
            if self.is_ec2_underutilised(filter_params, resource_data) or \
               self.no_filter(filter_params):
                exceeded.append(resource_data)

        return exceeded if exceeded else []

    @staticmethod
    def no_filter(filter_params):
        return filter_params['max_cpu'] is None and \
            filter_params['max_network'] is None and \
            filter_params['max_low_use_days'] is None and \
            filter_params['instance_types'] is None and \
            filter_params['min_savings'] is None

    @staticmethod
    def is_ec2_underutilised(filter_params, resource_data):
        """
        Method compares the filter constraints against a passed resources
        values and if the resource meets the criteria of the filter it
        returns True, otherwise false.
        """

        instance_types = filter_params['instance_types']
        resource_inst_type = resource_data['instance type']
        if instance_types and resource_inst_type not in instance_types:
            return False

        max_cpu = filter_params['max_cpu']
        resource_cpu = resource_data['average CPU'].replace('%', '')
        if max_cpu and float(resource_cpu) > max_cpu:
            return False

        max_network = filter_params['max_network']
        resource_network = resource_data['average network io']
        resource_network = resource_network.replace('MB', '')
        if max_network and float(resource_network) > max_network:
            return False

        min_savings = filter_params['min_savings']
        resource_savings = resource_data['estimated monthly savings']
        resource_savings = resource_savings.replace('$', '')
        if min_savings and float(resource_savings) < min_savings:
            return False

        max_low_use_days = filter_params['max_low_use_days']
        low_use = resource_data['low utilization days']
        low_use = low_use.replace(' days', '')
        return not(max_low_use_days and int(low_use) > max_low_use_days)
