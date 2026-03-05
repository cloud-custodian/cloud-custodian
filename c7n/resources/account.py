# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""AWS Account as a custodian resource.
"""
import json
import time
import datetime
from contextlib import suppress
from botocore.exceptions import ClientError
from fnmatch import fnmatch
from dateutil.parser import parse as parse_date
from dateutil.tz import tzutc

from c7n.actions import ActionRegistry, BaseAction
from c7n.exceptions import PolicyValidationError
from c7n.filters import Filter, FilterRegistry, ValueFilter
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters.multiattr import MultiAttrFilter
from c7n.filters.missing import Missing
from c7n.manager import resources
from c7n.utils import local_session, type_schema, generate_arn, get_support_region, jmespath_search
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.filters import ListItemFilter

from c7n.resources.iam import CredentialReport
from c7n.resources.securityhub import OtherResourcePostFinding

from .aws import shape_validate, Arn

filters = FilterRegistry('aws.account.filters')
actions = ActionRegistry('aws.account.actions')

retry = staticmethod(QueryResourceManager.retry)
filters.register('missing', Missing)


class DescribeAccount(DescribeSource):

    def get_account(self):
        client = local_session(self.manager.session_factory).client("iam")
        aliases = client.list_account_aliases().get(
            'AccountAliases', ('',))
        name = aliases and aliases[0] or ""
        return {'account_id': self.manager.config.account_id,
                'account_name': name}

    def resources(self, query=None):
        return [self.get_account()]

    def get_resources(self, resource_ids):
        return [self.get_account()]


@resources.register('account')
class Account(QueryResourceManager):

    filter_registry = filters
    action_registry = actions
    retry = staticmethod(QueryResourceManager.retry)
    source_type = 'describe'

    class resource_type(TypeInfo):
        id = 'account_id'
        name = 'account_name'
        filter_name = None
        global_resource = True
        # fake this for doc gen
        service = "account"
        # for posting config rule evaluations
        cfn_type = 'AWS::::Account'

    source_mapping = {
        'describe': DescribeAccount
    }

    @classmethod
    def get_permissions(cls):
        return ('iam:ListAccountAliases',)

    @classmethod
    def has_arn(cls):
        return True

    def get_arns(self, resources):
        return ["arn:::{account_id}".format(**r) for r in resources]


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
            if self.match(r, info):
                r['c7n:credential-report'] = info
                results.append(r)
        return results


@filters.register('organization')
class AccountOrganization(ValueFilter):
    """Check organization enrollment and configuration

    :example:

    determine if an account is not in an organization

    .. code-block:: yaml

      policies:
        - name: no-org
          resource: account
          filters:
            - type: organization
              key: Id
              value: absent


    :example:

    determine if an account is setup for organization policies

    .. code-block:: yaml

       policies:
         - name: org-policies-not-enabled
           resource: account
           filters:
             - type: organization
               key: FeatureSet
               value: ALL
               op: not-equal
    """
    schema = type_schema('organization', rinherit=ValueFilter.schema)
    schema_alias = False

    annotation_key = 'c7n:org'
    annotate = False

    permissions = ('organizations:DescribeOrganization',)

    def get_org_info(self, account):
        client = local_session(
            self.manager.session_factory).client('organizations')
        try:
            org_info = client.describe_organization().get('Organization')
        except client.exceptions.AWSOrganizationsNotInUseException:
            org_info = {}
        except ClientError as e:
            self.log.warning('organization filter error accessing org info %s', e)
            org_info = None
        account[self.annotation_key] = org_info

    def process(self, resources, event=None):
        if self.annotation_key not in resources[0]:
            self.get_org_info(resources[0])
        # if we can't access org info, we've already logged, and return
        if resources[0][self.annotation_key] is None:
            return []
        if super().process([resources[0][self.annotation_key]]):
            return resources
        return []


@filters.register('check-macie')
class MacieEnabled(ValueFilter):
    """Check status of macie v2 in the account.

    Gets the macie session info for the account, and
    the macie adminstrator account for the current account if
    configured.
    """

    schema = type_schema('check-macie', rinherit=ValueFilter.schema)
    schema_alias = False
    annotation_key = 'c7n:macie'
    annotate = False
    permissions = ('macie2:GetMacieSession', 'macie2:GetAdministratorAccount',)

    def process(self, resources, event=None):

        if self.annotation_key not in resources[0]:
            self.get_macie_info(resources[0])

        if super().process([resources[0][self.annotation_key]]):
            return resources

        return []

    def get_macie_info(self, account):
        client = local_session(
            self.manager.session_factory).client('macie2')

        try:
            info = client.get_macie_session()
            info.pop('ResponseMetadata')
        except client.exceptions.AccessDeniedException:
            info = {}

        try:
            minfo = client.get_administrator_account().get('administrator')
        except (client.exceptions.AccessDeniedException,
                client.exceptions.ResourceNotFoundException):
            info['master'] = {}
        else:
            info['master'] = minfo
        info['administrator'] = info['master']
        account[self.annotation_key] = info


@filters.register('check-cloudtrail')
class CloudTrailEnabled(Filter):
    """Verify cloud trail enabled for this account per specifications.

    Returns an annotated account resource if trail is not enabled.

    Of particular note, the current-region option will evaluate whether cloudtrail is available
    in the current region, either as a multi region trail or as a trail with it as the home region.

    The log-metric-filter-pattern option checks for the existence of a cloudwatch alarm and a
    corresponding SNS subscription for a specific filter pattern

    :example:

    .. code-block:: yaml

            policies:
              - name: account-cloudtrail-enabled
                resource: account
                region: us-east-1
                filters:
                  - type: check-cloudtrail
                    global-events: true
                    multi-region: true
                    running: true
                    include-management-events: true
                    log-metric-filter-pattern: "{ ($.eventName = \\"ConsoleLogin\\") }"

    Check for CloudWatch log group with a metric filter that has a filter pattern
    matching a regex pattern:

    .. code-block:: yaml

            policies:
              - name: account-cloudtrail-with-matching-log-metric-filter
                resource: account
                region: us-east-1
                filters:
                  - type: check-cloudtrail
                    log-metric-filter-pattern:
                        type: value
                        op: regex
                        value: '\\{ ?(\\()? ?\\$\\.eventName ?= ?(")?ConsoleLogin(")? ?(\\))? ?\\}'
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
           'kms-key': {'type': 'string'},
           'include-management-events': {'type': 'boolean'},
           'log-metric-filter-pattern':  {'oneOf': [
                {'$ref': '#/definitions/filters/value'},
                {'type': 'string'}]}})

    permissions = ('cloudtrail:DescribeTrails', 'cloudtrail:GetTrailStatus',
                   'cloudtrail:GetEventSelectors', 'cloudwatch:DescribeAlarmsForMetric',
                   'logs:DescribeMetricFilters', 'sns:GetTopicAttributes')

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)
        client = session.client('cloudtrail')
        trails = client.describe_trails()['trailList']
        resources[0]['c7n:cloudtrails'] = trails

        if self.data.get('global-events'):
            trails = [t for t in trails if t.get('IncludeGlobalServiceEvents')]
        if self.data.get('current-region'):
            current_region = session.region_name
            trails = [t for t in trails if t.get(
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
            trails = [t for t in trails if t.get('SnsTopicARN')]
        if self.data.get('running', True):
            running = []
            for t in list(trails):
                t['Status'] = status = client.get_trail_status(
                    Name=t['TrailARN'])
                if status['IsLogging'] and not status.get(
                        'LatestDeliveryError'):
                    running.append(t)
            trails = running
        if self.data.get('include-management-events'):
            matched = []
            for t in list(trails):
                selectors = client.get_event_selectors(TrailName=t['TrailARN'])
                if 'EventSelectors' in selectors.keys():
                    for s in selectors['EventSelectors']:
                        if s['IncludeManagementEvents'] and s['ReadWriteType'] == 'All':
                            matched.append(t)
                elif 'AdvancedEventSelectors' in selectors.keys():
                    for s in selectors['AdvancedEventSelectors']:
                        management = False
                        readonly = False
                        for field_selector in s['FieldSelectors']:
                            if field_selector['Field'] == 'eventCategory' and \
                                    'Management' in field_selector['Equals']:
                                management = True
                            elif field_selector['Field'] == 'readOnly':
                                readonly = True
                        if management and not readonly:
                            matched.append(t)

            trails = matched
        if self.data.get('log-metric-filter-pattern'):
            client_logs = session.client('logs')
            client_cw = session.client('cloudwatch')
            client_sns = session.client('sns')
            matched = []
            pattern = self.data.get('log-metric-filter-pattern')
            if isinstance(pattern, str):
                vf = ValueFilter({'key': 'filterPattern', 'value': pattern})
            else:
                pattern.setdefault('key', 'filterPattern')
                vf = ValueFilter(pattern)

            for t in list(trails):
                if 'CloudWatchLogsLogGroupArn' not in t.keys():
                    continue
                log_group_name = t['CloudWatchLogsLogGroupArn'].split(':')[6]
                try:
                    metric_filters_log_group = \
                        client_logs.describe_metric_filters(
                            logGroupName=log_group_name)['metricFilters']
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ResourceNotFoundException':
                        continue
                filter_matched = None
                if metric_filters_log_group:
                    for f in metric_filters_log_group:
                        if vf(f):
                            filter_matched = f
                            break
                if not filter_matched:
                    continue
                alarms = client_cw.describe_alarms_for_metric(
                    MetricName=filter_matched["metricTransformations"][0]["metricName"],
                    Namespace=filter_matched["metricTransformations"][0]["metricNamespace"]
                )['MetricAlarms']
                alarm_actions = []
                for a in alarms:
                    alarm_actions.extend(a['AlarmActions'])
                if not alarm_actions:
                    continue
                alarm_actions = set(alarm_actions)
                for a in alarm_actions:
                    try:
                        sns_topic_attributes = client_sns.get_topic_attributes(TopicArn=a)
                        sns_topic_attributes = sns_topic_attributes.get('Attributes')
                        if sns_topic_attributes.get('SubscriptionsConfirmed', '0') != '0':
                            matched.append(t)
                    except client_sns.exceptions.InvalidParameterValueException:
                        # we can ignore any exception here, the alarm action might
                        # not be an sns topic for instance
                        continue
            trails = matched
        if trails:
            return []
        return resources


@filters.register('guard-duty')
class GuardDutyEnabled(MultiAttrFilter):
    """Check if the guard duty service is enabled.

    This allows looking at account's detector and its associated
    master if any.

    :example:

     Check to ensure guard duty is active on account and associated to a master.

    .. code-block:: yaml

            policies:
              - name: guardduty-enabled
                resource: account
                filters:
                  - type: guard-duty
                    Detector.Status: ENABLED
                    Administrator.AccountId: "00011001"
                    Administrator.RelationshipStatus: "Enabled"
    """

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['guard-duty']},
            'match-operator': {'enum': ['or', 'and']}},
        'patternProperties': {
            '^Detector': {'oneOf': [{'type': 'object'}, {'type': 'string'}]},
            '^Administrator': {'oneOf': [{'type': 'object'}, {'type': 'string'}]}},
    }

    annotation = "c7n:guard-duty"
    permissions = (
        'guardduty:GetAdministratorAccount',
        'guardduty:ListDetectors',
        'guardduty:GetDetector')

    def validate(self):
        attrs = set()
        for k in self.data:
            if k.startswith('Detector') or k.startswith('Administrator'):
                attrs.add(k)
        self.multi_attrs = attrs
        return super(GuardDutyEnabled, self).validate()

    def get_target(self, resource):
        if self.annotation in resource:
            return resource[self.annotation]

        client = local_session(self.manager.session_factory).client('guardduty')
        # detectors are singletons too.
        detector_ids = client.list_detectors().get('DetectorIds')

        if not detector_ids:
            return None
        else:
            detector_id = detector_ids.pop()

        detector = client.get_detector(DetectorId=detector_id)
        detector.pop('ResponseMetadata', None)
        admin = client.get_administrator_account(DetectorId=detector_id).get('Administrator')
        resource[self.annotation] = r = {'Detector': detector, 'Administrator': admin}
        return r


@filters.register('check-config')
class ConfigEnabled(Filter):
    """Is config service enabled for this account

    :example:

    .. code-block:: yaml

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

    .. code-block:: yaml

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
    schema_alias = False
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


@filters.register('access-analyzer')
class AccessAnalyzer(ValueFilter):
    """Check for access analyzers in an account

    :example:

    .. code-block:: yaml

      policies:
        - name: account-access-analyzer
          resource: account
          filters:
            - type: access-analyzer
              key: 'status'
              value: ACTIVE
              op: eq
    """

    schema = type_schema('access-analyzer', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('access-analyzer:ListAnalyzers',)
    annotation_key = 'c7n:matched-analyzers'

    def process(self, resources, event=None):
        account = resources[0]
        if not account.get(self.annotation_key):
            client = local_session(self.manager.session_factory).client('accessanalyzer')
            analyzers = self.manager.retry(client.list_analyzers)['analyzers']
        else:
            analyzers = account.get(self.annotation_key)

        matched_analyzers = []
        for analyzer in analyzers:
            if self.match(analyzer):
                matched_analyzers.append(analyzer)
        account[self.annotation_key] = matched_analyzers
        return matched_analyzers and resources or []


@filters.register('password-policy')
class AccountPasswordPolicy(ValueFilter):
    """Check an account's password policy.

    Note that on top of the default password policy fields, we also add an extra key,
    PasswordPolicyConfigured which will be set to true or false to signify if the given
    account has attempted to set a policy at all.

    :example:

    .. code-block:: yaml

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
    schema_alias = False
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


@actions.register('set-password-policy')
class SetAccountPasswordPolicy(BaseAction):
    """Set an account's password policy.

    This only changes the policy for the items provided.
    If this is the first time setting a password policy and an item is not provided it will be
    set to the defaults defined in the boto docs for IAM.Client.update_account_password_policy

    :example:

    .. code-block:: yaml

            policies:
              - name: set-account-password-policy
                resource: account
                filters:
                  - not:
                    - type: password-policy
                      key: MinimumPasswordLength
                      value: 10
                      op: ge
                actions:
                    - type: set-password-policy
                      policy:
                        MinimumPasswordLength: 20
    """
    schema = type_schema(
        'set-password-policy',
        policy={
            'type': 'object'
        })
    shape = 'UpdateAccountPasswordPolicyRequest'
    service = 'iam'
    permissions = ('iam:GetAccountPasswordPolicy', 'iam:UpdateAccountPasswordPolicy')

    def validate(self):
        return shape_validate(
            self.data.get('policy', {}),
            self.shape,
            self.service)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iam')
        account = resources[0]
        if account.get('c7n:password_policy'):
            config = account['c7n:password_policy']
        else:
            try:
                config = client.get_account_password_policy().get('PasswordPolicy')
            except client.exceptions.NoSuchEntityException:
                config = {}
        params = dict(self.data['policy'])
        config.update(params)
        config = {k: v for (k, v) in config.items() if k not in ('ExpirePasswords',
            'PasswordPolicyConfigured')}
        client.update_account_password_policy(**config)


@filters.register('service-limit')
class ServiceLimit(Filter):
    """Check if account's service limits are past a given threshold.

    Supported limits are per trusted advisor, which is variable based
    on usage in the account and support level enabled on the account.

    The `names` attribute lets you filter which checks to query limits
    about.  This is a case-insensitive globbing match on a check name.
    You can specify a name exactly or use globbing wildcards like `VPC*`.

    The names are exactly what's shown on the trusted advisor page:

        https://console.aws.amazon.com/trustedadvisor/home#/category/service-limits

    or via the awscli:

        aws --region us-east-1 support describe-trusted-advisor-checks --language en \
            --query 'checks[?category==`service_limits`].[name]' --output text

    While you can target individual checks via the `names` attribute, and
    that should be the preferred method, the following are provided for
    backward compatibility with the old style of checks:

    - `services`

        The resulting limit's `service` field must match one of these.
        These are case-insensitive globbing matches.

        Note: If you haven't specified any `names` to filter, then
        these service names are used as a case-insensitive prefix match on
        the check name.  This helps limit the number of API calls we need
        to make.

    - `limits`

        The resulting limit's `Limit Name` field must match one of these.
        These are case-insensitive globbing matches.

    Some example names and their corresponding service and limit names:

    Check Name                          Service         Limit Name
    ----------------------------------  --------------  ---------------------------------
    Auto Scaling Groups                 AutoScaling     Auto Scaling groups
    Auto Scaling Launch Configurations  AutoScaling     Launch configurations
    CloudFormation Stacks               CloudFormation  Stacks
    ELB Application Load Balancers      ELB             Active Application Load Balancers
    ELB Classic Load Balancers          ELB             Active load balancers
    ELB Network Load Balancers          ELB             Active Network Load Balancers
    VPC                                 VPC             VPCs
    VPC Elastic IP Address              VPC             VPC Elastic IP addresses (EIPs)
    VPC Internet Gateways               VPC             Internet gateways

    Note: Some service limits checks are being migrated to service quotas,
    which is expected to largely replace service limit checks in trusted
    advisor.  In this case, some of these checks have no results.

    :example:

    .. code-block:: yaml

            policies:
              - name: specific-account-service-limits
                resource: account
                filters:
                  - type: service-limit
                    names:
                      - IAM Policies
                      - IAM Roles
                      - "VPC*"
                    threshold: 1.0

              - name: increase-account-service-limits
                resource: account
                filters:
                  - type: service-limit
                    services:
                      - EC2
                    threshold: 1.0

              - name: specify-region-for-global-service
                region: us-east-1
                resource: account
                filters:
                  - type: service-limit
                    services:
                      - IAM
                    limits:
                      - Roles
    """

    schema = type_schema(
        'service-limit',
        threshold={'type': 'number'},
        refresh_period={'type': 'integer',
                        'title': 'how long should a check result be considered fresh'},
        names={'type': 'array', 'items': {'type': 'string'}},
        limits={'type': 'array', 'items': {'type': 'string'}},
        services={'type': 'array', 'items': {
            'enum': ['AutoScaling', 'CloudFormation',
                     'DynamoDB', 'EBS', 'EC2', 'ELB',
                     'IAM', 'RDS', 'Route53', 'SES', 'VPC']}})

    permissions = ('support:DescribeTrustedAdvisorCheckRefreshStatuses',
                   'support:DescribeTrustedAdvisorCheckResult',
                   'support:DescribeTrustedAdvisorChecks',
                   'support:RefreshTrustedAdvisorCheck')
    deprecated_check_ids = ['eW7HH0l7J9']
    check_limit = ('region', 'service', 'check', 'limit', 'extant', 'color')

    # When doing a refresh, how long to wait for the check to become ready.
    # Max wait here is 5 * 10 ~ 50 seconds.
    poll_interval = 5
    poll_max_intervals = 10
    global_services = {'IAM'}

    def validate(self):
        region = self.manager.data.get('region', '')
        if len(self.global_services.intersection(self.data.get('services', []))):
            if region != 'us-east-1':
                raise PolicyValidationError(
                    "Global services: %s must be targeted in us-east-1 on the policy"
                    % ', '.join(self.global_services))
        return self

    @classmethod
    def get_check_result(cls, client, check_id):
        checks = client.describe_trusted_advisor_check_result(
            checkId=check_id, language='en')['result']

        # Check status and if necessary refresh checks
        if checks['status'] == 'not_available':
            try:
                client.refresh_trusted_advisor_check(checkId=check_id)
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvalidParameterValueException':
                    cls.log.warning("InvalidParameterValueException: %s",
                     e.response['Error']['Message'])
                    return

            for _ in range(cls.poll_max_intervals):
                time.sleep(cls.poll_interval)
                refresh_response = client.describe_trusted_advisor_check_refresh_statuses(
                    checkIds=[check_id])
                if refresh_response['statuses'][0]['status'] == 'success':
                    checks = client.describe_trusted_advisor_check_result(
                        checkId=check_id, language='en')['result']
                    break
        return checks

    def get_available_checks(self, client, category='service_limits'):
        checks = client.describe_trusted_advisor_checks(language='en')
        return [c for c in checks['checks']
                if c['category'] == category and
                c['id'] not in self.deprecated_check_ids]

    def match_patterns_to_value(self, patterns, value):
        for p in patterns:
            if fnmatch(value.lower(), p.lower()):
                return True
        return False

    def should_process(self, name):
        # if names specified, limit to these names
        patterns = self.data.get('names')
        if patterns:
            return self.match_patterns_to_value(patterns, name)

        # otherwise, if services specified, limit to those prefixes
        services = self.data.get('services')
        if services:
            patterns = ["{}*".format(i) for i in services]
            return self.match_patterns_to_value(patterns, name.replace(' ', ''))

        return True

    def process(self, resources, event=None):
        support_region = get_support_region(self.manager)
        client = local_session(self.manager.session_factory).client(
            'support', region_name=support_region)
        checks = self.get_available_checks(client)
        exceeded = []
        for check in checks:
            if not self.should_process(check['name']):
                continue
            matched = self.process_check(client, check, resources, event)
            if matched:
                for m in matched:
                    m['check_id'] = check['id']
                    m['name'] = check['name']
                exceeded.extend(matched)
        if exceeded:
            resources[0]['c7n:ServiceLimitsExceeded'] = exceeded
            return resources
        return []

    def process_check(self, client, check, resources, event=None):
        region = self.manager.config.region
        results = self.get_check_result(client, check['id'])

        if results is None or 'flaggedResources' not in results:
            return []

        # trim to only results for this region
        results['flaggedResources'] = [
            r
            for r in results.get('flaggedResources', [])
            if r['metadata'][0] == region or (r['metadata'][0] == '-' and region == 'us-east-1')
        ]

        # save all raw limit results to the account resource
        if 'c7n:ServiceLimits' not in resources[0]:
            resources[0]['c7n:ServiceLimits'] = []
        resources[0]['c7n:ServiceLimits'].append(results)

        # check if we need to refresh the check for next time
        delta = datetime.timedelta(self.data.get('refresh_period', 1))
        check_date = parse_date(results['timestamp'])
        if datetime.datetime.now(tz=tzutc()) - delta > check_date:
            try:
                client.refresh_trusted_advisor_check(checkId=check['id'])
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvalidParameterValueException':
                    self.log.warning("InvalidParameterValueException: %s",
                     e.response['Error']['Message'])
                    return

        services = self.data.get('services')
        limits = self.data.get('limits')
        threshold = self.data.get('threshold')
        exceeded = []

        for resource in results['flaggedResources']:
            if threshold is None and resource['status'] == 'ok':
                continue
            limit = dict(zip(self.check_limit, resource['metadata']))
            if services and not self.match_patterns_to_value(services, limit['service']):
                continue
            if limits and not self.match_patterns_to_value(limits, limit['check']):
                continue
            limit['status'] = resource['status']
            limit['percentage'] = (
                float(limit['extant'] or 0) / float(limit['limit']) * 100
            )
            if threshold and limit['percentage'] < threshold:
                continue
            exceeded.append(limit)
        return exceeded


@actions.register('request-limit-increase')
class RequestLimitIncrease(BaseAction):
    r"""File support ticket to raise limit.

    :Example:

    .. code-block:: yaml

        policies:
          - name: raise-account-service-limits
            resource: account
            filters:
              - type: service-limit
                services:
                  - EBS
                limits:
                  - Provisioned IOPS (SSD) storage (GiB)
                threshold: 60.5
            actions:
              - type: request-limit-increase
                notify: [email, email2]
                ## You can use one of either percent-increase or an amount-increase.
                percent-increase: 50
                message: "Please raise the below account limit(s); \n {limits}"
    """

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['request-limit-increase']},
            'percent-increase': {'type': 'number', 'minimum': 1},
            'amount-increase': {'type': 'number', 'minimum': 1},
            'minimum-increase': {'type': 'number', 'minimum': 1},
            'subject': {'type': 'string'},
            'message': {'type': 'string'},
            'notify': {'type': 'array', 'items': {'type': 'string'}},
            'severity': {'type': 'string', 'enum': ['urgent', 'high', 'normal', 'low']}
        },
        'oneOf': [
            {'required': ['type', 'percent-increase']},
            {'required': ['type', 'amount-increase']}
        ]
    }

    permissions = ('support:CreateCase',)

    default_subject = '[Account:{account}]Raise the following limit(s) of {service} in {region}'
    default_template = 'Please raise the below account limit(s); \n {limits}'
    default_severity = 'normal'

    service_code_mapping = {
        'AutoScaling': 'auto-scaling',
        'CloudFormation': 'aws-cloudformation',
        'DynamoDB': 'amazon-dynamodb',
        'EBS': 'amazon-elastic-block-store',
        'EC2': 'amazon-elastic-compute-cloud-linux',
        'ELB': 'elastic-load-balancing',
        'IAM': 'aws-identity-and-access-management',
        'Kinesis': 'amazon-kinesis',
        'RDS': 'amazon-relational-database-service-aurora',
        'Route53': 'amazon-route53',
        'SES': 'amazon-simple-email-service',
        'VPC': 'amazon-virtual-private-cloud',
    }

    def process(self, resources):
        support_region = get_support_region(self.manager)
        client = local_session(self.manager.session_factory).client(
            'support', region_name=support_region)
        account_id = self.manager.config.account_id
        service_map = {}
        region_map = {}
        limit_exceeded = resources[0].get('c7n:ServiceLimitsExceeded', [])
        percent_increase = self.data.get('percent-increase')
        amount_increase = self.data.get('amount-increase')
        minimum_increase = self.data.get('minimum-increase', 1)

        for s in limit_exceeded:
            current_limit = int(s['limit'])
            if percent_increase:
                increase_by = current_limit * float(percent_increase) / 100
                increase_by = max(increase_by, minimum_increase)
            else:
                increase_by = amount_increase
            increase_by = round(increase_by)
            msg = '\nIncrease %s by %d in %s \n\t Current Limit: %s\n\t Current Usage: %s\n\t ' \
                  'Set New Limit to: %d' % (
                      s['check'], increase_by, s['region'], s['limit'], s['extant'],
                      (current_limit + increase_by))
            service_map.setdefault(s['service'], []).append(msg)
            region_map.setdefault(s['service'], s['region'])

        for service in service_map:
            subject = self.data.get('subject', self.default_subject).format(
                service=service, region=region_map[service], account=account_id)
            service_code = self.service_code_mapping.get(service)
            body = self.data.get('message', self.default_template)
            body = body.format(**{
                'service': service,
                'limits': '\n\t'.join(service_map[service]),
            })
            client.create_case(
                subject=subject,
                communicationBody=body,
                serviceCode=service_code,
                categoryCode='general-guidance',
                severityCode=self.data.get('severity', self.default_severity),
                ccEmailAddresses=self.data.get('notify', []))


def cloudtrail_policy(original, bucket_name, account_id, bucket_region):
    '''add CloudTrail permissions to an S3 policy, preserving existing'''
    ct_actions = [
        {
            'Action': 's3:GetBucketAcl',
            'Effect': 'Allow',
            'Principal': {'Service': 'cloudtrail.amazonaws.com'},
            'Resource': generate_arn(
                service='s3', resource=bucket_name, region=bucket_region),
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
            'Resource': generate_arn(
                service='s3', resource=bucket_name, region=bucket_region),
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


# AWS Account doesn't participate in events (not based on query resource manager)
# so the event subscriber used by postfinding to register doesn't apply, manually
# register it.
Account.action_registry.register('post-finding', OtherResourcePostFinding)


@actions.register('enable-cloudtrail')
class EnableTrail(BaseAction):
    """Enables logging on the trail(s) named in the policy

    :Example:

    .. code-block:: yaml

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
            'bucket-region': {'type': 'string'},
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
        bucket_region = self.data.get('bucket-region', 'us-east-1')
        trail_name = self.data.get('trail', 'default-trail')
        multi_region = self.data.get('multi-region', True)
        global_events = self.data.get('global-events', True)
        notify = self.data.get('notify', '')
        file_digest = self.data.get('file-digest', False)
        kms = self.data.get('kms', False)
        kms_key = self.data.get('kms-key', '')

        s3client = session.client('s3', region_name=bucket_region)
        try:
            s3client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': bucket_region}
            )
        except ClientError as ce:
            if not ('Error' in ce.response and
            ce.response['Error']['Code'] == 'BucketAlreadyOwnedByYou'):
                raise ce

        try:
            current_policy = s3client.get_bucket_policy(Bucket=bucket_name)
        except ClientError:
            current_policy = None

        policy_json = cloudtrail_policy(
            current_policy, bucket_name,
            self.manager.config.account_id, bucket_region)

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

    .. code-block:: yaml

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
        mfa_user = mfa.get('User', {}).get('Arn', '').split(':')[-1]
        return mfa_user == 'root'

    def account_has_virtual_mfa(self, account):
        if not account.get('c7n:VirtualMFADevices'):
            client = local_session(self.manager.session_factory).client('iam')
            paginator = client.get_paginator('list_virtual_mfa_devices')
            raw_list = paginator.paginate().build_full_result()['VirtualMFADevices']
            account['c7n:VirtualMFADevices'] = list(filter(
                self.mfa_belongs_to_root_account, raw_list))
        expect_virtual_mfa = self.data.get('value', True)
        has_virtual_mfa = any(account['c7n:VirtualMFADevices'])
        return expect_virtual_mfa == has_virtual_mfa

    def process(self, resources, event=None):
        return list(filter(self.account_has_virtual_mfa, resources))


@actions.register('enable-data-events')
class EnableDataEvents(BaseAction):
    """Ensure all buckets in account are setup to log data events.

    Note this works via a single trail for data events per
    https://aws.amazon.com/about-aws/whats-new/2017/09/aws-cloudtrail-enables-option-to-add-all-amazon-s3-buckets-to-data-events/

    This trail should NOT be used for api management events, the
    configuration here is soley for data events. If directed to create
    a trail this will do so without management events.

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-enable-data-events-logging
                resource: account
                actions:
                 - type: enable-data-events
                   data-trail:
                     name: s3-events
                     multi-region: us-east-1
    """

    schema = type_schema(
        'enable-data-events', required=['data-trail'], **{
            'data-trail': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['name'],
                'properties': {
                    'create': {
                        'title': 'Should we create trail if needed for events?',
                        'type': 'boolean'},
                    'type': {'enum': ['ReadOnly', 'WriteOnly', 'All']},
                    'name': {
                        'title': 'The name of the event trail',
                        'type': 'string'},
                    'topic': {
                        'title': 'If creating, the sns topic for the trail to send updates',
                        'type': 'string'},
                    's3-bucket': {
                        'title': 'If creating, the bucket to store trail event data',
                        'type': 'string'},
                    's3-prefix': {'type': 'string'},
                    'key-id': {
                        'title': 'If creating, Enable kms on the trail',
                        'type': 'string'},
                    # region that we're aggregating via trails.
                    'multi-region': {
                        'title': 'If creating, use this region for all data trails',
                        'type': 'string'}}}})

    def validate(self):
        if self.data['data-trail'].get('create'):
            if 's3-bucket' not in self.data['data-trail']:
                raise PolicyValidationError(
                    "If creating data trails, an s3-bucket is required on %s" % (
                        self.manager.data))
        return self

    def get_permissions(self):
        perms = [
            'cloudtrail:DescribeTrails',
            'cloudtrail:GetEventSelectors',
            'cloudtrail:PutEventSelectors']

        if self.data.get('data-trail', {}).get('create'):
            perms.extend([
                'cloudtrail:CreateTrail', 'cloudtrail:StartLogging'])
        return perms

    def add_data_trail(self, client, trail_cfg):
        if not trail_cfg.get('create'):
            raise ValueError(
                "s3 data event trail missing and not configured to create")
        params = dict(
            Name=trail_cfg['name'],
            S3BucketName=trail_cfg['s3-bucket'],
            EnableLogFileValidation=True)

        if 'key-id' in trail_cfg:
            params['KmsKeyId'] = trail_cfg['key-id']
        if 's3-prefix' in trail_cfg:
            params['S3KeyPrefix'] = trail_cfg['s3-prefix']
        if 'topic' in trail_cfg:
            params['SnsTopicName'] = trail_cfg['topic']
        if 'multi-region' in trail_cfg:
            params['IsMultiRegionTrail'] = True

        client.create_trail(**params)
        return {'Name': trail_cfg['name']}

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        region = self.data['data-trail'].get('multi-region')

        if region:
            client = session.client('cloudtrail', region_name=region)
        else:
            client = session.client('cloudtrail')

        added = False
        tconfig = self.data['data-trail']
        trails = client.describe_trails(
            trailNameList=[tconfig['name']]).get('trailList', ())
        if not trails:
            trail = self.add_data_trail(client, tconfig)
            added = True
        else:
            trail = trails[0]

        events = client.get_event_selectors(
            TrailName=trail['Name']).get('EventSelectors', [])

        for e in events:
            found = False
            if not e.get('DataResources'):
                continue
            for data_events in e['DataResources']:
                if data_events['Type'] != 'AWS::S3::Object':
                    continue
                for b in data_events['Values']:
                    if b.rsplit(':')[-1].strip('/') == '':
                        found = True
                        break
            if found:
                resources[0]['c7n_data_trail'] = trail
                return

        # Opinionated choice, separate api and data events.
        event_count = len(events)
        events = [e for e in events if not e.get('IncludeManagementEvents')]
        if len(events) != event_count:
            self.log.warning("removing api trail from data trail")

        # future proof'd for other data events, for s3 this trail
        # encompasses all the buckets in the account.

        events.append({
            'IncludeManagementEvents': False,
            'ReadWriteType': tconfig.get('type', 'All'),
            'DataResources': [{
                'Type': 'AWS::S3::Object',
                'Values': ['arn:aws:s3:::']}]})
        client.put_event_selectors(
            TrailName=trail['Name'],
            EventSelectors=events)

        if added:
            client.start_logging(Name=tconfig['name'])

        resources[0]['c7n_data_trail'] = trail


@filters.register('shield-enabled')
class ShieldEnabled(Filter):

    permissions = ('shield:DescribeSubscription',)

    schema = type_schema(
        'shield-enabled',
        state={'type': 'boolean'})

    def process(self, resources, event=None):
        state = self.data.get('state', False)
        client = local_session(self.manager.session_factory).client('shield')
        try:
            subscription = client.describe_subscription().get(
                'Subscription', None)
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                raise
            subscription = None

        resources[0]['c7n:ShieldSubscription'] = subscription
        if state and subscription:
            return resources
        elif not state and not subscription:
            return resources
        return []


@actions.register('set-shield-advanced')
class SetShieldAdvanced(BaseAction):
    """Enable/disable Shield Advanced on an account."""

    permissions = (
        'shield:CreateSubscription', 'shield:DeleteSubscription')

    schema = type_schema(
        'set-shield-advanced',
        state={'type': 'boolean'})

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('shield')
        state = self.data.get('state', True)

        if state:
            client.create_subscription()
        else:
            try:
                client.delete_subscription()
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    return
                raise


@filters.register('xray-encrypt-key')
class XrayEncrypted(Filter):
    """Determine if xray is encrypted.

    :example:

    .. code-block:: yaml

            policies:
              - name: xray-encrypt-with-default
                resource: aws.account
                filters:
                   - type: xray-encrypt-key
                     key: default
              - name: xray-encrypt-with-kms
                resource: aws.account
                filters:
                   - type: xray-encrypt-key
                     key: kms
              - name: xray-encrypt-with-specific-key
                resource: aws.account
                filters:
                   - type: xray-encrypt-key
                     key: alias/my-alias or arn or keyid
    """

    permissions = ('xray:GetEncryptionConfig',)
    schema = type_schema(
        'xray-encrypt-key',
        required=['key'],
        key={'type': 'string'}
    )

    def process(self, resources, event=None):
        client = self.manager.session_factory().client('xray')
        gec_result = client.get_encryption_config()['EncryptionConfig']
        resources[0]['c7n:XrayEncryptionConfig'] = gec_result

        k = self.data.get('key')
        if k not in ['default', 'kms']:
            kmsclient = self.manager.session_factory().client('kms')
            keyid = kmsclient.describe_key(KeyId=k)['KeyMetadata']['Arn']
            rc = resources if (gec_result['KeyId'] == keyid) else []
        else:
            kv = 'KMS' if self.data.get('key') == 'kms' else 'NONE'
            rc = resources if (gec_result['Type'] == kv) else []
        return rc


@actions.register('set-xray-encrypt')
class SetXrayEncryption(BaseAction):
    """Enable specific xray encryption.

    :example:

    .. code-block:: yaml

            policies:
              - name: xray-default-encrypt
                resource: aws.account
                actions:
                  - type: set-xray-encrypt
                    key: default
              - name: xray-kms-encrypt
                resource: aws.account
                actions:
                  - type: set-xray-encrypt
                    key: alias/some/alias/key
    """

    permissions = ('xray:PutEncryptionConfig',)
    schema = type_schema(
        'set-xray-encrypt',
        required=['key'],
        key={'type': 'string'}
    )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('xray')
        key = self.data.get('key')
        req = {'Type': 'NONE'} if key == 'default' else {'Type': 'KMS', 'KeyId': key}
        client.put_encryption_config(**req)


@filters.register('default-ebs-encryption')
class EbsEncryption(Filter):
    """Filter an account by its ebs encryption status.

    By default for key we match on the alias name for a key.

    :example:

    .. code-block:: yaml

       policies:
         - name: check-default-ebs-encryption
           resource: aws.account
           filters:
            - type: default-ebs-encryption
              key: "alias/aws/ebs"
              state: true

    It is also possible to match on specific key attributes (tags, origin)

    :example:

    .. code-block:: yaml

       policies:
         - name: check-ebs-encryption-key-origin
           resource: aws.account
           filters:
            - type: default-ebs-encryption
              key:
                type: value
                key: Origin
                value: AWS_KMS
              state: true
    """
    permissions = ('ec2:GetEbsEncryptionByDefault',)
    schema = type_schema(
        'default-ebs-encryption',
        state={'type': 'boolean'},
        key={'oneOf': [
            {'$ref': '#/definitions/filters/value'},
            {'type': 'string'}]})

    def process(self, resources, event=None):
        state = self.data.get('state', False)
        client = local_session(self.manager.session_factory).client('ec2')
        account_state = client.get_ebs_encryption_by_default().get(
            'EbsEncryptionByDefault')
        if account_state != state:
            return []
        if state and 'key' in self.data:
            vfd = (isinstance(self.data['key'], dict) and
                   self.data['key'] or {'c7n:AliasName': self.data['key']})
            vf = KmsRelatedFilter(vfd, self.manager)
            vf.RelatedIdsExpression = 'KmsKeyId'
            vf.annotate = False
            key = client.get_ebs_default_kms_key_id().get('KmsKeyId')
            if not vf.process([{'KmsKeyId': key}]):
                return []
        return resources


@actions.register('set-ebs-encryption')
class SetEbsEncryption(BaseAction):
    """Set AWS EBS default encryption on an account

    :example:

    .. code-block:: yaml

       policies:
         - name: set-default-ebs-encryption
           resource: aws.account
           filters:
            - type: default-ebs-encryption
              state: false
           actions:
            - type: set-ebs-encryption
              state: true
              key: alias/aws/ebs
    """
    permissions = ('ec2:EnableEbsEncryptionByDefault',
                   'ec2:DisableEbsEncryptionByDefault')

    schema = type_schema(
        'set-ebs-encryption',
        state={'type': 'boolean'},
        key={'type': 'string'})

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('ec2')
        state = self.data.get('state')
        key = self.data.get('key')
        if state:
            client.enable_ebs_encryption_by_default()
        else:
            client.disable_ebs_encryption_by_default()

        if state and key:
            client.modify_ebs_default_kms_key_id(
                KmsKeyId=self.data['key'])


@filters.register('s3-public-block')
class S3PublicBlock(ValueFilter):
    """Check for s3 public blocks on an account.

    https://docs.aws.amazon.com/AmazonS3/latest/dev/access-control-block-public-access.html
    """

    annotation_key = 'c7n:s3-public-block'
    annotate = False  # no annotation from value filter
    schema = type_schema('s3-public-block', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('s3:GetAccountPublicAccessBlock',)

    def process(self, resources, event=None):
        self.augment([r for r in resources if self.annotation_key not in r])
        return super(S3PublicBlock, self).process(resources, event)

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('s3control')
        for r in resources:
            try:
                r[self.annotation_key] = client.get_public_access_block(
                    AccountId=r['account_id']).get('PublicAccessBlockConfiguration', {})
            except client.exceptions.NoSuchPublicAccessBlockConfiguration:
                r[self.annotation_key] = {}

    def __call__(self, r):
        return super(S3PublicBlock, self).__call__(r[self.annotation_key])


@actions.register('set-s3-public-block')
class SetS3PublicBlock(BaseAction):
    """Configure S3 Public Access Block on an account.

    All public access block attributes can be set. If not specified they are merged
    with the extant configuration.

    https://docs.aws.amazon.com/AmazonS3/latest/dev/access-control-block-public-access.html

    :example:

    .. yaml:

      policies:
        - name: restrict-public-buckets
          resource: aws.account
          filters:
            - not:
               - type: s3-public-block
                 key: RestrictPublicBuckets
                 value: true
          actions:
            - type: set-s3-public-block
              RestrictPublicBuckets: true

    """
    schema = type_schema(
        'set-s3-public-block',
        state={'type': 'boolean', 'default': True},
        BlockPublicAcls={'type': 'boolean'},
        IgnorePublicAcls={'type': 'boolean'},
        BlockPublicPolicy={'type': 'boolean'},
        RestrictPublicBuckets={'type': 'boolean'})

    permissions = ('s3:PutAccountPublicAccessBlock', 's3:GetAccountPublicAccessBlock')

    def validate(self):
        config = self.data.copy()
        config.pop('type')
        if config.pop('state', None) is False and config:
            raise PolicyValidationError(
                "{} cant set state false with controls specified".format(
                    self.type))

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('s3control')
        if self.data.get('state', True) is False:
            for r in resources:
                client.delete_public_access_block(AccountId=r['account_id'])
            return

        keys = (
            'BlockPublicPolicy', 'BlockPublicAcls', 'IgnorePublicAcls', 'RestrictPublicBuckets')

        for r in resources:
            # try to merge with existing configuration if not explicitly set.
            base = {}
            if S3PublicBlock.annotation_key in r:
                base = r[S3PublicBlock.annotation_key]
            else:
                try:
                    base = client.get_public_access_block(AccountId=r['account_id']).get(
                        'PublicAccessBlockConfiguration')
                except client.exceptions.NoSuchPublicAccessBlockConfiguration:
                    base = {}

            config = {}
            for k in keys:
                if k in self.data:
                    config[k] = self.data[k]
                elif k in base:
                    config[k] = base[k]

            client.put_public_access_block(
                AccountId=r['account_id'],
                PublicAccessBlockConfiguration=config)


@filters.register('ami-block-public-access')
class AmiBlockPublicAccess(Filter):
    """Scans for AWS accounts that have/do not have Block Public Access set for
    their AMIs.

    :example:

    .. code-block:: yaml

            policies:
              - name: unblocked-ami-block-public-access
                resource: aws.account
                filters:
                  - type: ami-block-public-access
                    value: false

    """

    annotation_key = 'c7n:ami-block-public-access'
    schema = type_schema('ami-block-public-access', value={'type': 'boolean'})
    permissions = ('ec2:GetImageBlockPublicAccessState',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ec2')
        is_blocked = self.data.get('value', False)
        results = []

        # Get account-wide block public access state
        response = client.get_image_block_public_access_state()
        account_state = response.get('ImageBlockPublicAccessState', 'unblocked')
        account_blocked = account_state == 'block-new-sharing'

        for r in resources:
            r[self.annotation_key] = account_blocked

            # Filter resources based on whether the account state matches the desired value
            if account_blocked == is_blocked:
                results.append(r)

        return results


class GlueCatalogEncryptionEnabled(MultiAttrFilter):
    """ Filter glue catalog by its glue encryption status and KMS key

    :example:

    .. code-block:: yaml

      policies:
        - name: glue-catalog-security-config
          resource: aws.glue-catalog
          filters:
            - type: glue-security-config
              SseAwsKmsKeyId: alias/aws/glue

    """
    retry = staticmethod(QueryResourceManager.retry)

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['glue-security-config']},
            'CatalogEncryptionMode': {'enum': ['DISABLED', 'SSE-KMS']},
            'SseAwsKmsKeyId': {'type': 'string'},
            'ReturnConnectionPasswordEncrypted': {'type': 'boolean'},
            'AwsKmsKeyId': {'type': 'string'}
        }
    }

    annotation = "c7n:glue-security-config"
    permissions = ('glue:GetDataCatalogEncryptionSettings',)

    def validate(self):
        attrs = set()
        for key in self.data:
            if key in ['CatalogEncryptionMode',
                       'ReturnConnectionPasswordEncrypted',
                       'SseAwsKmsKeyId',
                       'AwsKmsKeyId']:
                attrs.add(key)
        self.multi_attrs = attrs
        return super(GlueCatalogEncryptionEnabled, self).validate()

    def get_target(self, resource):
        if self.annotation in resource:
            return resource[self.annotation]
        client = local_session(self.manager.session_factory).client('glue')
        encryption_setting = resource.get('DataCatalogEncryptionSettings')
        if self.manager.type != 'glue-catalog':
            encryption_setting = client.get_data_catalog_encryption_settings().get(
                'DataCatalogEncryptionSettings')
        resource[self.annotation] = encryption_setting.get('EncryptionAtRest')
        resource[self.annotation].update(encryption_setting.get('ConnectionPasswordEncryption'))
        key_attrs = ('SseAwsKmsKeyId', 'AwsKmsKeyId')
        for encrypt_attr in key_attrs:
            if encrypt_attr not in self.data or not self.data[encrypt_attr].startswith('alias'):
                continue
            key = resource[self.annotation].get(encrypt_attr)
            vfd = {'c7n:AliasName': self.data[encrypt_attr]}
            vf = KmsRelatedFilter(vfd, self.manager)
            vf.RelatedIdsExpression = 'KmsKeyId'
            vf.annotate = False
            if not vf.process([{'KmsKeyId': key}]):
                return []
            resource[self.annotation][encrypt_attr] = self.data[encrypt_attr]
        return resource[self.annotation]


@filters.register('glue-security-config')
class AccountCatalogEncryptionFilter(GlueCatalogEncryptionEnabled):
    """Filter aws account by its glue encryption status and KMS key

    :example:

    .. code-block:: yaml

      policies:
        - name: glue-security-config
          resource: aws.account
          filters:
            - type: glue-security-config
              SseAwsKmsKeyId: alias/aws/glue

    """


@filters.register('emr-block-public-access')
class EMRBlockPublicAccessConfiguration(ValueFilter):
    """Check for EMR block public access configuration on an account

    :example:

    .. code-block:: yaml

            policies:
              - name: get-emr-block-public-access
                resource: account
                filters:
                  - type: emr-block-public-access
    """

    annotation_key = 'c7n:emr-block-public-access'
    annotate = False  # no annotation from value filter
    schema = type_schema('emr-block-public-access', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ("elasticmapreduce:GetBlockPublicAccessConfiguration",)

    def process(self, resources, event=None):
        self.augment([r for r in resources if self.annotation_key not in r])
        return super().process(resources, event)

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client(
            'emr', region_name=self.manager.config.region)

        for r in resources:
            r[self.annotation_key] = self.manager.retry(
                client.get_block_public_access_configuration)
            r[self.annotation_key].pop('ResponseMetadata')

    def __call__(self, r):
        return super(EMRBlockPublicAccessConfiguration, self).__call__(r[self.annotation_key])


@actions.register('set-emr-block-public-access')
class PutAccountBlockPublicAccessConfiguration(BaseAction):
    """Action to put/update the EMR block public access configuration for your
       AWS account in the current region

    :example:

    .. code-block:: yaml

            policies:
              - name: set-emr-block-public-access
                resource: account
                filters:
                  - type: emr-block-public-access
                    key: BlockPublicAccessConfiguration.BlockPublicSecurityGroupRules
                    value: False
                actions:
                  - type: set-emr-block-public-access
                    config:
                        BlockPublicSecurityGroupRules: True
                        PermittedPublicSecurityGroupRuleRanges:
                            - MinRange: 22
                              MaxRange: 22
                            - MinRange: 23
                              MaxRange: 23

    """

    schema = type_schema('set-emr-block-public-access',
                         config={"type": "object",
                            'properties': {
                                'BlockPublicSecurityGroupRules': {'type': 'boolean'},
                                'PermittedPublicSecurityGroupRuleRanges': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'MinRange': {'type': 'number', "minimum": 0},
                                            'MaxRange': {'type': 'number', "minimum": 0}
                                        },
                                        'required': ['MinRange']
                                    }
                                }
                            },
                             'required': ['BlockPublicSecurityGroupRules']
                         },
                         required=('config',))

    permissions = ("elasticmapreduce:PutBlockPublicAccessConfiguration",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('emr')
        r = resources[0]

        base = {}
        if EMRBlockPublicAccessConfiguration.annotation_key in r:
            base = r[EMRBlockPublicAccessConfiguration.annotation_key]
        else:
            try:
                base = client.get_block_public_access_configuration()
                base.pop('ResponseMetadata')
            except client.exceptions.NoSuchPublicAccessBlockConfiguration:
                base = {}

        config = base['BlockPublicAccessConfiguration']
        updatedConfig = {**config, **self.data.get('config')}

        if config == updatedConfig:
            return

        client.put_block_public_access_configuration(
            BlockPublicAccessConfiguration=updatedConfig
        )


@filters.register('securityhub')
class SecHubEnabled(Filter):
    """Filter an account depending on whether security hub is enabled or not.

    :example:

    .. code-block:: yaml

       policies:
         - name: check-securityhub-status
           resource: aws.account
           filters:
            - type: securityhub
              enabled: true

    """

    permissions = ('securityhub:DescribeHub',)

    schema = type_schema('securityhub', enabled={'type': 'boolean'})

    def process(self, resources, event=None):
        state = self.data.get('enabled', True)
        client = local_session(self.manager.session_factory).client('securityhub')
        sechub = self.manager.retry(client.describe_hub, ignore_err_codes=(
            'InvalidAccessException',))
        if state == bool(sechub):
            return resources
        return []


@filters.register('lakeformation-s3-cross-account')
class LakeformationFilter(Filter):
    """Flags an account if its using a lakeformation s3 bucket resource from a different account.

    :example:

    .. code-block:: yaml

       policies:
         - name: lakeformation-cross-account-bucket
           resource: aws.account
           filters:
            - type: lakeformation-s3-cross-account

    """

    schema = type_schema('lakeformation-s3-cross-account', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('lakeformation:ListResources',)
    annotation = 'c7n:lake-cross-account-s3'

    def process(self, resources, event=None):
        results = []
        for r in resources:
            if self.process_account(r):
                results.append(r)
        return results

    def process_account(self, account):
        client = local_session(self.manager.session_factory).client('lakeformation')
        lake_buckets = {
            Arn.parse(r).resource for r in jmespath_search(
                'ResourceInfoList[].ResourceArn',
                client.list_resources())
        }
        buckets = {
            b['Name'] for b in
            self.manager.get_resource_manager('s3').resources(augment=False)}
        cross_account = lake_buckets.difference(buckets)
        if not cross_account:
            return False
        account[self.annotation] = list(cross_account)
        return True


@actions.register('toggle-config-managed-rule')
class ToggleConfigManagedRule(BaseAction):
    """Enables or disables an AWS Config Managed Rule

    :example:

    .. code-block:: yaml

        policies:
          - name: config-managed-s3-bucket-public-write-remediate-event
            description: |
              This policy detects if S3 bucket allows public write by the bucket policy
              or ACL and remediates.
            comment: |
              This policy detects if S3 bucket policy or ACL allows public write access.
              When the bucket is evaluated as 'NON_COMPLIANT', the action
              'AWS-DisableS3BucketPublicReadWrite' is triggered and remediates.
            resource: account
            filters:
              - type: missing
                policy:
                  resource: config-rule
                  filters:
                    - type: remediation
                      rule_name: &rule_name 'config-managed-s3-bucket-public-write-remediate-event'
                      remediation: &remediation-config
                        TargetId: AWS-DisableS3BucketPublicReadWrite
                        Automatic: true
                        MaximumAutomaticAttempts: 5
                        RetryAttemptSeconds: 211
                        Parameters:
                          AutomationAssumeRole:
                            StaticValue:
                              Values:
                                - 'arn:aws:iam::{account_id}:role/myrole'
                          S3BucketName:
                            ResourceValue:
                              Value: RESOURCE_ID
            actions:
              - type: toggle-config-managed-rule
                rule_name: *rule_name
                managed_rule_id: S3_BUCKET_PUBLIC_WRITE_PROHIBITED
                resource_types:
                  - 'AWS::S3::Bucket'
                rule_parameters: '{}'
                remediation: *remediation-config
    """

    permissions = (
        'config:DescribeConfigRules',
        'config:DescribeRemediationConfigurations',
        'config:PutRemediationConfigurations',
        'config:PutConfigRule',
    )

    schema = type_schema('toggle-config-managed-rule',
        enabled={'type': 'boolean', 'default': True},
        rule_name={'type': 'string'},
        rule_prefix={'type': 'string'},
        managed_rule_id={'type': 'string'},
        resource_types={'type': 'array', 'items':
                        {'pattern': '^AWS::*', 'type': 'string'}},
        resource_tag={
            'type': 'object',
            'properties': {
                'key': {'type': 'string'},
                'value': {'type': 'string'},
            },
            'required': ['key', 'value'],
        },
        resource_id={'type': 'string'},
        rule_parameters={'type': 'string'},
        remediation={
            'type': 'object',
            'properties': {
                'TargetType': {'type': 'string'},
                'TargetId': {'type': 'string'},
                'Automatic': {'type': 'boolean'},
                'Parameters': {'type': 'object'},
                'MaximumAutomaticAttempts': {
                    'type': 'integer',
                    'minimum': 1, 'maximum': 25,
                },
                'RetryAttemptSeconds': {
                    'type': 'integer',
                    'minimum': 1, 'maximum': 2678000,
                },
                'ExecutionControls': {'type': 'object'},
            },
        },
        tags={'type': 'object'},
        required=['rule_name'],
    )

    def validate(self):
        if (
            self.data.get('enabled', True) and
            not self.data.get('managed_rule_id')
        ):
            raise PolicyValidationError("managed_rule_id required to enable a managed rule")
        return self

    def process(self, accounts):
        client = local_session(self.manager.session_factory).client('config')
        rule = self.ConfigManagedRule(self.data)
        params = self.get_rule_params(rule)

        if self.data.get('enabled', True):
            client.put_config_rule(**params)

            if rule.remediation:
                remediation_params = self.get_remediation_params(rule)
                client.put_remediation_configurations(
                    RemediationConfigurations=[remediation_params]
                )
        else:
            with suppress(client.exceptions.NoSuchRemediationConfigurationException):
                client.delete_remediation_configuration(
                    ConfigRuleName=rule.name
                )

            with suppress(client.exceptions.NoSuchConfigRuleException):
                client.delete_config_rule(
                    ConfigRuleName=rule.name
                )

    def get_rule_params(self, rule):
        params = dict(
            ConfigRuleName=rule.name,
            Description=rule.description,
            Source={
                'Owner': 'AWS',
                'SourceIdentifier': rule.managed_rule_id,
            },
            InputParameters=rule.rule_parameters
        )

        # A config rule scope can include one or more resource types,
        # a combination of a tag key and value, or a combination of
        # one resource type and one resource ID
        params.update({'Scope': {'ComplianceResourceTypes': rule.resource_types}})
        if rule.resource_tag:
            params.update({'Scope': {
                'TagKey': rule.resource_tag['key'],
                'TagValue': rule.resource_tag['value']}
            })
        elif rule.resource_id:
            params.update({'Scope': {'ComplianceResourceId': rule.resource_id}})

        return dict(ConfigRule=params)

    def get_remediation_params(self, rule):
        rule.remediation['ConfigRuleName'] = rule.name
        if 'TargetType' not in rule.remediation:
            rule.remediation['TargetType'] = 'SSM_DOCUMENT'
        return rule.remediation

    class ConfigManagedRule:
        """Wraps the action data into an AWS Config Managed Rule.
        """

        def __init__(self, data):
            self.data = data

        @property
        def name(self):
            prefix = self.data.get('rule_prefix', 'custodian-')
            return "%s%s" % (prefix, self.data.get('rule_name', ''))

        @property
        def description(self):
            return self.data.get(
                'description', 'cloud-custodian AWS Config Managed Rule policy')

        @property
        def tags(self):
            return self.data.get('tags', {})

        @property
        def resource_types(self):
            return self.data.get('resource_types', [])

        @property
        def managed_rule_id(self):
            return self.data.get('managed_rule_id', '')

        @property
        def resource_tag(self):
            return self.data.get('resource_tag', {})

        @property
        def resource_id(self):
            return self.data.get('resource_id', '')

        @property
        def rule_parameters(self):
            return self.data.get('rule_parameters', '')

        @property
        def remediation(self):
            return self.data.get('remediation', {})


@filters.register('ses-agg-send-stats')
class SesAggStats(ValueFilter):
    """This filter queries SES send statistics and aggregates all
    the data points into a single report.

    :example:

    .. code-block:: yaml

            policies:
              - name: ses-aggregated-send-stats-policy
                resource: account
                filters:
                  - type: ses-agg-send-stats
    """

    schema = type_schema('ses-agg-send-stats', rinherit=ValueFilter.schema)
    annotation_key = 'c7n:ses-send-agg'
    permissions = ("ses:GetSendStatistics",)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ses')
        get_send_stats = client.get_send_statistics()
        results = []

        if not get_send_stats or not get_send_stats.get('SendDataPoints'):
            return results

        resource_counter = {'DeliveryAttempts': 0,
                            'Bounces': 0,
                            'Complaints': 0,
                            'Rejects': 0,
                            'BounceRate': 0}
        for d in get_send_stats.get('SendDataPoints', []):
            resource_counter['DeliveryAttempts'] += d['DeliveryAttempts']
            resource_counter['Bounces'] += d['Bounces']
            resource_counter['Complaints'] += d['Complaints']
            resource_counter['Rejects'] += d['Rejects']
        resource_counter['BounceRate'] = round(
            (resource_counter['Bounces'] /
             resource_counter['DeliveryAttempts']) * 100)
        resources[0][self.annotation_key] = resource_counter

        return resources


@filters.register('ses-send-stats')
class SesConsecutiveStats(Filter):
    """This filter annotates the account resource with SES send statistics for the
    last n number of days, not including the current date.

    The stats are aggregated into daily metrics. Additionally, the filter also
    calculates and annotates the max daily bounce rate (percentage). Using this filter,
    users can alert when the bounce rate for a particular day is higher than the limit.

    :example:

    .. code-block:: yaml

            policies:
              - name: ses-send-stats
                resource: account
                filters:
                  - type: ses-send-stats
                    days: 5
                  - type: value
                    key: '"c7n:ses-max-bounce-rate"'
                    op: ge
                    value: 10
    """
    schema = type_schema('ses-send-stats', days={'type': 'number', 'minimum': 2},
                         required=['days'])
    send_stats_annotation = 'c7n:ses-send-stats'
    max_bounce_annotation = 'c7n:ses-max-bounce-rate'
    permissions = ("ses:GetSendStatistics",)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ses')
        get_send_stats = client.get_send_statistics()
        results = []
        check_days = self.data.get('days', 2)
        utcnow = datetime.datetime.utcnow()
        expected_dates = set()

        for days in range(1, check_days + 1):
            expected_dates.add((utcnow - datetime.timedelta(days=days)).strftime('%Y-%m-%d'))

        if not get_send_stats or not get_send_stats.get('SendDataPoints'):
            return results

        metrics = {}
        for d in get_send_stats.get('SendDataPoints', []):
            ts = d['Timestamp'].strftime('%Y-%m-%d')
            if ts not in expected_dates:
                continue

            if not metrics.get(ts):
                metrics[ts] = {'DeliveryAttempts': 0,
                               'Bounces': 0,
                               'Complaints': 0,
                               'Rejects': 0}
            metrics[ts]['DeliveryAttempts'] += d['DeliveryAttempts']
            metrics[ts]['Bounces'] += d['Bounces']
            metrics[ts]['Complaints'] += d['Complaints']
            metrics[ts]['Rejects'] += d['Rejects']

        max_bounce_rate = 0
        for ts, metric in metrics.items():
            metric['BounceRate'] = round((metric['Bounces'] / metric['DeliveryAttempts']) * 100)
            if max_bounce_rate < metric['BounceRate']:
                max_bounce_rate = metric['BounceRate']
            metric['Date'] = ts

        resources[0][self.send_stats_annotation] = list(metrics.values())
        resources[0][self.max_bounce_annotation] = max_bounce_rate

        return resources


@filters.register('bedrock-model-invocation-logging')
class BedrockModelInvocationLogging(ListItemFilter):
    """Filter for account to look at bedrock model invocation logging configuration

    The schema to supply to the attrs follows the schema here:
     https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock/client/get_model_invocation_logging_configuration.html

    :example:

    .. code-block:: yaml

            policies:
              - name: bedrock-model-invocation-logging-configuration
                resource: account
                filters:
                  - type: bedrock-model-invocation-logging
                    attrs:
                      - imageDataDeliveryEnabled: True

    """
    schema = type_schema(
        'bedrock-model-invocation-logging',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )
    permissions = ('bedrock:GetModelInvocationLoggingConfiguration',)
    annotation_key = 'c7n:BedrockModelInvocationLogging'

    def get_item_values(self, resource):
        item_values = []
        client = local_session(self.manager.session_factory).client('bedrock')
        invocation_logging_config = client \
                .get_model_invocation_logging_configuration().get('loggingConfig')
        if invocation_logging_config is not None:
            item_values.append(invocation_logging_config)
            resource[self.annotation_key] = invocation_logging_config
        return item_values


@actions.register('set-bedrock-model-invocation-logging')
class SetBedrockModelInvocationLogging(BaseAction):
    """Set Bedrock Model Invocation Logging Configuration on an account.
     https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock/client/put_model_invocation_logging_configuration.html

     To delete a configuration, supply enabled to False

    :example:

    .. code-block:: yaml

            policies:
              - name: set-bedrock-model-invocation-logging
                resource: account
                actions:
                  - type: set-bedrock-model-invocation-logging
                    enabled: True
                    loggingConfig:
                      textDataDeliveryEnabled: True
                      s3Config:
                        bucketName: test-bedrock-1
                        keyPrefix:  logging/

              - name: delete-bedrock-model-invocation-logging
                resource: account
                actions:
                  - type: set-bedrock-model-invocation-logging
                    enabled: False
    """

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['set-bedrock-model-invocation-logging']},
            'enabled': {'type': 'boolean'},
            'loggingConfig': {'type': 'object'}
        },
    }

    permissions = ('bedrock:PutModelInvocationLoggingConfiguration',)
    shape = 'PutModelInvocationLoggingConfigurationRequest'
    service = 'bedrock'

    def validate(self):
        cfg = dict(self.data)
        enabled = cfg.get('enabled')
        if enabled:
            cfg.pop('type')
            cfg.pop('enabled')
            return shape_validate(
                cfg,
                self.shape,
                self.service)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('bedrock')
        if self.data.get('enabled'):
            params = self.data.get('loggingConfig')
            client.put_model_invocation_logging_configuration(loggingConfig=params)
        else:
            client.delete_model_invocation_logging_configuration()


@filters.register('ec2-metadata-defaults')
class EC2MetadataDefaults(ValueFilter):
    """Filter on the default instance metadata service (IMDS) settings for the specified account and
    region.  NOTE: Any configuration that has never been set (or is set to 'No Preference'), will
    not be returned in the response.

    :example:

    .. code-block:: yaml

            policies:
              - name: ec2-imds-defaults
                resource: account
                filters:
                - or:
                  - type: ec2-metadata-defaults
                    key: HttpTokens
                    value: optional
                  - type: ec2-metadata-defaults
                    key: HttpTokens
                    value: absent
    """

    annotation_key = 'c7n:EC2MetadataDefaults'
    annotate = False  # no annotation from value filter
    schema = type_schema('ec2-metadata-defaults', rinherit=ValueFilter.schema)
    permissions = ('ec2:GetInstanceMetadataDefaults',)

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            r[self.annotation_key] = self.manager.retry(
                client.get_instance_metadata_defaults)["AccountLevel"]

    def process(self, resources, event=None):
        self.augment([r for r in resources if self.annotation_key not in r])
        return super(EC2MetadataDefaults, self).process(resources, event)

    def __call__(self, r):
        return super(EC2MetadataDefaults, self).__call__(r[self.annotation_key])


@actions.register('set-ec2-metadata-defaults')
class SetEC2MetadataDefaults(BaseAction):
    """Modifies the default instance metadata service (IMDS) settings at the account level.

    :example:

    .. code-block:: yaml

            policies:
              - name: set-ec2-metadata-defaults
                resource: account
                filters:
                  - or:
                    - type: ec2-metadata-defaults
                      key: HttpTokens
                      op: eq
                      value: optional
                    - type: ec2-metadata-defaults
                      key: HttpTokens
                      value: absent
                actions:
                  - type: set-ec2-metadata-defaults
                    HttpTokens: required

    """

    schema = type_schema(
        'set-ec2-metadata-defaults',
        HttpTokens={'enum': ['optional', 'required', 'no-preference']},
        HttpPutResponseHopLimit={'type': 'integer'},
        HttpEndpoint={'enum': ['enabled', 'disabled', 'no-preference']},
        InstanceMetadataTags={'enum': ['enabled', 'disabled', 'no-preference']},
    )

    permissions = ('ec2:ModifyInstanceMetadataDefaults',)
    service = 'ec2'
    shape = 'ModifyInstanceMetadataDefaultsRequest'

    def validate(self):
        req = dict(self.data)
        req.pop('type')
        return shape_validate(
            req, self.shape, self.service
        )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client(self.service)
        self.data.pop('type')
        client.modify_instance_metadata_defaults(**self.data)


@actions.register('set-security-token-service-preferences')
class SetSecurityTokenServicePreferences(BaseAction):
    """Action to set STS preferences."""

    """Action to set STS preferences.

    :example:

    .. code-block:: yaml

            policies:
              - name: set-sts-preferences
                resource: account
                filters:
                  - or:
                    - type: iam-summary
                      key: GlobalEndpointTokenVersion
                      value: absent
                      value: optional
                    - type: iam-summary
                      key: GlobalEndpointTokenVersion
                      op: ne
                      value: 2
                actions:
                  - type: set-security-token-service-preferences
                    token_version: v2Token

    """

    schema = type_schema(
        'set-security-token-service-preferences',
        token_version={'type': 'string', 'enum': ['v1Token', 'v2Token']}
    )

    permissions = ('iam:SetSecurityTokenServicePreferences',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iam')
        token_version = self.data.get('token_version', 'v2Token')
        for resource in resources:
            self.set_sts_preferences(client, token_version)

    def set_sts_preferences(self, client, token_version):
        client.set_security_token_service_preferences(
            GlobalEndpointTokenVersion=token_version
        )
