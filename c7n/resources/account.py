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
from __future__ import absolute_import, division, print_function, unicode_literals

import json
from botocore.exceptions import ClientError
from datetime import datetime, timedelta

from dateutil.parser import parse as parse_date
from dateutil.tz import tzutc

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import Filter, FilterRegistry, ValueFilter
from c7n.manager import ResourceManager, resources
from c7n.utils import local_session, type_schema

from c7n.resources.iam import CredentialReport


filters = FilterRegistry('aws.account.actions')
actions = ActionRegistry('aws.account.filters')


def get_account(session_factory, config):
    session = local_session(session_factory)
    client = session.client('iam')
    aliases = client.list_account_aliases().get(
        'AccountAliases', ('',))
    name = aliases and aliases[0] or ""
    return {'account_id': config.account_id,
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
        return self.filter_resources([get_account(self.session_factory, self.config)])

    def get_resources(self, resource_ids):
        return [get_account(self.session_factory, self.config)]


@filters.register('credential')
class AccountCredentialReport(CredentialReport):

    def process(self, resources, event=None):
        super(AccountCredentialReport, self).process(resources, event)
        report = self.get_credential_report()
        if report is None:
            return []
        results = []
        info = report.get('<root_account>')
        for r in resources:
            if self.match(info):
                r['c7n:credential-report'] = info
                results.append(r)
        return results


@filters.register('check-cloudtrail')
class CloudTrailEnabled(Filter):
    """Verify cloud trail enabled for this account per specifications.

    Returns an annotated account resource if trail is not enabled.

    Of particular note, the current-region option will evaluate whether cloudtrail is available
    in the current region, either as a multi region trail or as a trail with it as the home region.

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
           'current-region': {'type': 'boolean'},
           'running': {'type': 'boolean'},
           'notifies': {'type': 'boolean'},
           'file-digest': {'type': 'boolean'},
           'kms': {'type': 'boolean'},
           'kms-key': {'type': 'string'}})

    permissions = ('cloudtrail:DescribeTrails', 'cloudtrail:GetTrailStatus')

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)
        client = session.client('cloudtrail')
        trails = client.describe_trails()['trailList']
        resources[0]['c7n:cloudtrails'] = trails
        if self.data.get('global-events'):
            trails = [t for t in trails if t.get('IncludeGlobalServiceEvents')]
        if self.data.get('current-region'):
            current_region = session.region_name
            trails  = [t for t in trails if t.get(
                'HomeRegion') == current_region or t.get('IsMultiRegionTrail')]
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
            recorders = [r for r in recorders if status[r['name']]['recording'] and
                status[r['name']]['lastStatus'].lower() in ('pending', 'success')]
        if channels and recorders:
            return []
        return resources


@filters.register('iam-summary')
class IAMSummary(ValueFilter):
    """Return annotated account resource if iam summary filter matches.

    Some use cases include, detecting root api keys or mfa usage.

    Example iam summary wrt to matchable fields::

      {
            "AccessKeysPerUserQuota": 2,
            "AccountAccessKeysPresent": 0,
            "AccountMFAEnabled": 1,
            "AccountSigningCertificatesPresent": 0,
            "AssumeRolePolicySizeQuota": 2048,
            "AttachedPoliciesPerGroupQuota": 10,
            "AttachedPoliciesPerRoleQuota": 10,
            "AttachedPoliciesPerUserQuota": 10,
            "GroupPolicySizeQuota": 5120,
            "Groups": 1,
            "GroupsPerUserQuota": 10,
            "GroupsQuota": 100,
            "InstanceProfiles": 0,
            "InstanceProfilesQuota": 100,
            "MFADevices": 3,
            "MFADevicesInUse": 2,
            "Policies": 3,
            "PoliciesQuota": 1000,
            "PolicySizeQuota": 5120,
            "PolicyVersionsInUse": 5,
            "PolicyVersionsInUseQuota": 10000,
            "Providers": 0,
            "RolePolicySizeQuota": 10240,
            "Roles": 4,
            "RolesQuota": 250,
            "ServerCertificates": 0,
            "ServerCertificatesQuota": 20,
            "SigningCertificatesPerUserQuota": 2,
            "UserPolicySizeQuota": 2048,
            "Users": 5,
            "UsersQuota": 5000,
            "VersionsPerPolicyQuota": 5,
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
    """Check an account's password policy.

    Note that on top of the default password policy fields, we also add an extra key,
    PasswordPolicyConfigured which will be set to true or false to signify if the given
    account has attempted to set a policy at all.

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
        account = resources[0]
        if not account.get('c7n:password_policy'):
            client = local_session(self.manager.session_factory).client('iam')
            policy = {}
            try:
                policy = client.get_account_password_policy().get('PasswordPolicy', {})
                policy['PasswordPolicyConfigured'] = True
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchEntity':
                    policy['PasswordPolicyConfigured'] = False
                else:
                    raise
            account['c7n:password_policy'] = policy
        if self.match(account['c7n:password_policy']):
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
        delta = timedelta(self.data.get('refresh_period', 1))
        check_date = parse_date(checks['timestamp'])
        if datetime.now(tz=tzutc()) - delta > check_date:
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


@actions.register('request-limit-increase')
class RequestLimitIncrease(BaseAction):
    """ File support ticket to raise limit

    :Example:

    .. code-block: yaml

        policies:
          - name: account-service-limits
            resource: account
            filters:
             - type: service-limit
               services:
                 - EBS
               threshold: 60.5
             actions:
               - type: request-limit-increase
                 notify: [email, email2]
                 percent-increase: 50
                 message: "Raise {service} by {percent}%"
    """

    schema = type_schema(
        'request-limit-increase',
        **{'notify': {'type': 'array'},
           'percent-increase': {'type': 'number'},
           'subject': {'type': 'string'},
           'message': {'type': 'string'},
           'severity': {'type': 'string', 'enum': ['urgent', 'high', 'normal', 'low']},
           'required': ['percent-increase'],
           })

    permissions = ('support:CreateCase',)

    default_subject = 'Raise the account limit of {service}'
    default_template = 'Please raise the account limit of {service} by {percent}%'
    default_severity = 'normal'

    service_code_mapping = {
        'AutoScaling': 'auto-scaling',
        'ELB': 'elastic-load-balancing',
        'EBS': 'amazon-elastic-block-store',
        'EC2': 'amazon-elastic-compute-cloud-linux',
        'RDS': 'amazon-relational-database-service-aurora',
        'VPC': 'amazon-virtual-private-cloud',
    }

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        client = session.client('support')

        services_done = set()
        for resource in resources[0].get('c7n:ServiceLimitsExceeded', []):
            service = resource['service']
            if service in services_done:
                continue

            services_done.add(service)
            service_code = self.service_code_mapping.get(service)

            subject = self.data.get('subject', self.default_subject)
            subject = subject.format(service=service)

            body = self.data.get('message', self.default_template)
            body = body.format(**{
                'service': service,
                'percent': self.data.get('percent-increase')
            })

            client.create_case(
                subject=subject,
                communicationBody=body,
                serviceCode=service_code,
                categoryCode='general-guidance',
                severityCode=self.data.get('severity', self.default_severity),
                ccEmailAddresses=self.data.get('notify', []))


def cloudtrail_policy(original, bucket_name, account_id):
    '''add CloudTrail permissions to an S3 policy, preserving existing'''
    ct_actions = [
        {
            'Action': 's3:GetBucketAcl',
            'Effect': 'Allow',
            'Principal': {'Service': 'cloudtrail.amazonaws.com'},
            'Resource': 'arn:aws:s3:::' + bucket_name,
            'Sid': 'AWSCloudTrailAclCheck20150319',
        },
        {
            'Action': 's3:PutObject',
            'Condition': {
                'StringEquals':
                {'s3:x-amz-acl': 'bucket-owner-full-control'},
            },
            'Effect': 'Allow',
            'Principal': {'Service': 'cloudtrail.amazonaws.com'},
            'Resource': 'arn:aws:s3:::%s/AWSLogs/%s/*' % (
                bucket_name, account_id
            ),
            'Sid': 'AWSCloudTrailWrite20150319',
        },
    ]
    # parse original policy
    if original is None:
        policy = {
            'Statement': [],
            'Version': '2012-10-17',
        }
    else:
        policy = json.loads(original['Policy'])
    original_actions = [a.get('Action') for a in policy['Statement']]
    for cta in ct_actions:
        if cta['Action'] not in original_actions:
            policy['Statement'].append(cta)
    return json.dumps(policy)


@actions.register('enable-cloudtrail')
class EnableTrail(BaseAction):
    """Enables logging on the trail(s) named in the policy

    :Example:

    .. code-block: yaml

        policies:
          - name: trail-test
            description: Ensure CloudTrail logging is enabled
            resource: account
            actions:
              - type: enable-cloudtrail
                trail: mytrail
                bucket: trails
    """

    permissions = (
        'cloudtrail:CreateTrail',
        'cloudtrail:DescribeTrails',
        'cloudtrail:GetTrailStatus',
        'cloudtrail:StartLogging',
        'cloudtrail:UpdateTrail',
        's3:CreateBucket',
        's3:GetBucketPolicy',
        's3:PutBucketPolicy',
    )
    schema = type_schema(
        'enable-cloudtrail',
        **{
            'trail': {'type': 'string'},
            'bucket': {'type': 'string'},
            'multi-region': {'type': 'boolean'},
            'global-events': {'type': 'boolean'},
            'notify': {'type': 'string'},
            'file-digest': {'type': 'boolean'},
            'kms': {'type': 'boolean'},
            'kms-key': {'type': 'string'},
            'required': ('bucket',),
        }
    )

    def process(self, accounts):
        """Create or enable CloudTrail"""
        session = local_session(self.manager.session_factory)
        client = session.client('cloudtrail')
        bucket_name = self.data['bucket']
        trail_name = self.data.get('trail', 'default-trail')
        multi_region = self.data.get('multi-region', True)
        global_events = self.data.get('global-events', True)
        notify = self.data.get('notify', '')
        file_digest = self.data.get('file-digest', False)
        kms = self.data.get('kms', False)
        kms_key = self.data.get('kms-key', '')

        s3client = session.client('s3')
        s3client.create_bucket(Bucket=bucket_name)
        try:
            current_policy = s3client.get_bucket_policy(Bucket=bucket_name)
        except ClientError:
            current_policy = None

        policy_json = cloudtrail_policy(
            current_policy, bucket_name, self.manager.config.account_id)

        s3client.put_bucket_policy(Bucket=bucket_name, Policy=policy_json)
        trails = client.describe_trails().get('trailList', ())
        if trail_name not in [t.get('Name') for t in trails]:
            new_trail = client.create_trail(
                Name=trail_name,
                S3BucketName=bucket_name,
            )
            if new_trail:
                trails.append(new_trail)
                # the loop below will configure the new trail
        for trail in trails:
            if trail.get('Name') != trail_name:
                continue
            # enable
            arn = trail['TrailARN']
            status = client.get_trail_status(Name=arn)
            if not status['IsLogging']:
                client.start_logging(Name=arn)
            # apply configuration changes (if any)
            update_args = {}
            if multi_region != trail.get('IsMultiRegionTrail'):
                update_args['IsMultiRegionTrail'] = multi_region
            if global_events != trail.get('IncludeGlobalServiceEvents'):
                update_args['IncludeGlobalServiceEvents'] = global_events
            if notify != trail.get('SNSTopicArn'):
                update_args['SnsTopicName'] = notify
            if file_digest != trail.get('LogFileValidationEnabled'):
                update_args['EnableLogFileValidation'] = file_digest
            if kms_key != trail.get('KmsKeyId'):
                if not kms and 'KmsKeyId' in trail:
                    kms_key = ''
                update_args['KmsKeyId'] = kms_key
            if update_args:
                update_args['Name'] = trail_name
                client.update_trail(**update_args)


@filters.register('has-virtual-mfa')
class HasVirtualMFA(Filter):
    """Is the account configured with a virtual MFA device?

    :example:

        .. code-block: yaml

            policies:
                - name: account-with-virtual-mfa
                  resource: account
                  region: us-east-1
                  filters:
                    - type: has-virtual-mfa
                      value: true
    """

    schema = type_schema('has-virtual-mfa', **{'value': {'type': 'boolean'}})

    permissions = ('iam:ListVirtualMFADevices',)

    def mfa_belongs_to_root_account(self, mfa):
        return mfa['SerialNumber'].endswith(':mfa/root-account-mfa-device')

    def account_has_virtual_mfa(self, account):
        if not account.get('c7n:VirtualMFADevices'):
            client = local_session(self.manager.session_factory).client('iam')
            paginator = client.get_paginator('list_virtual_mfa_devices')
            raw_list = paginator.paginate().build_full_result()['VirtualMFADevices']
            account['c7n:VirtualMFADevices'] = filter(self.mfa_belongs_to_root_account, raw_list)
        expect_virtual_mfa = self.data.get('value', True)
        has_virtual_mfa = any(account['c7n:VirtualMFADevices'])
        return expect_virtual_mfa == has_virtual_mfa

    def process(self, resources, event=None):
        return filter(self.account_has_virtual_mfa, resources)
