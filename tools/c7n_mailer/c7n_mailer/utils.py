# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import base64
from datetime import datetime, timedelta
import functools
import json
import os
import time
import yaml

import jinja2
import jmespath
from botocore.exceptions import ClientError
from dateutil import parser
from dateutil.tz import gettz, tzutc


class Providers:
    AWS = 0
    Azure = 1


def get_jinja_env(template_folders):
    env = jinja2.Environment(trim_blocks=True, autoescape=False)
    env.filters['yaml_safe'] = functools.partial(yaml.safe_dump, default_flow_style=False)
    env.filters['date_time_format'] = date_time_format
    env.filters['get_date_time_delta'] = get_date_time_delta
    env.filters['from_json'] = json.loads
    env.filters['get_date_age'] = get_date_age
    env.globals['format_resource'] = resource_format
    env.globals['format_struct'] = format_struct
    env.globals['resource_tag'] = get_resource_tag_value
    env.globals['get_resource_tag_value'] = get_resource_tag_value
    env.globals['search'] = jmespath.search
    env.loader = jinja2.FileSystemLoader(template_folders)
    return env


def get_rendered_jinja(
        target, sqs_message, resources, logger,
        specified_template, default_template, template_folders):
    env = get_jinja_env(template_folders)
    mail_template = sqs_message['action'].get(specified_template, default_template)
    if not os.path.isabs(mail_template):
        mail_template = '%s.j2' % mail_template
    try:
        template = env.get_template(mail_template)
    except Exception as error_msg:
        logger.error("Invalid template reference %s\n%s" % (mail_template, error_msg))
        return

    # recast seconds since epoch as utc iso datestring, template
    # authors can use date_time_format helper func to convert local
    # tz. if no execution start time was passed use current time.
    execution_start = datetime.utcfromtimestamp(
        sqs_message.get(
            'execution_start',
            time.mktime(
                datetime.utcnow().timetuple())
        )).isoformat()

    rendered_jinja = template.render(
        recipient=target,
        resources=resources,
        account=sqs_message.get('account', ''),
        account_id=sqs_message.get('account_id', ''),
        event=sqs_message.get('event', None),
        action=sqs_message['action'],
        policy=sqs_message['policy'],
        execution_start=execution_start,
        region=sqs_message.get('region', ''))
    return rendered_jinja


# eg, target_tag_keys could be resource-owners ['Owners', 'SupportTeam']
# and this function would go through the resource and look for any tag keys
# that match Owners or SupportTeam, and return those values as targets
def get_resource_tag_targets(resource, target_tag_keys):
    if 'Tags' not in resource:
        return []
    if isinstance(resource['Tags'], dict):
        tags = resource['Tags']
    else:
        tags = {tag['Key']: tag['Value'] for tag in resource['Tags']}
    targets = []
    for target_tag_key in target_tag_keys:
        if target_tag_key in tags:
            targets.append(tags[target_tag_key])
    return targets


def get_message_subject(sqs_message):
    default_subject = 'Custodian notification - %s' % (sqs_message['policy']['name'])
    subject = sqs_message['action'].get('subject', default_subject)
    jinja_template = jinja2.Template(subject)
    subject = jinja_template.render(
        account=sqs_message.get('account', ''),
        account_id=sqs_message.get('account_id', ''),
        event=sqs_message.get('event', None),
        action=sqs_message['action'],
        policy=sqs_message['policy'],
        region=sqs_message.get('region', '')
    )
    return subject


def setup_defaults(config):
    config.setdefault('region', 'us-east-1')
    config.setdefault('ses_region', config.get('region'))
    config.setdefault('memory', 1024)
    config.setdefault('runtime', 'python3.7')
    config.setdefault('timeout', 300)
    config.setdefault('subnets', None)
    config.setdefault('security_groups', None)
    config.setdefault('contact_tags', [])
    config.setdefault('ldap_uri', None)
    config.setdefault('ldap_bind_dn', None)
    config.setdefault('ldap_bind_user', None)
    config.setdefault('ldap_bind_password', None)
    config.setdefault('endpoint_url', None)
    config.setdefault('datadog_api_key', None)
    config.setdefault('slack_token', None)
    config.setdefault('slack_webhook', None)


def date_time_format(utc_str, tz_str='US/Eastern', format='%Y %b %d %H:%M %Z'):
    return parser.parse(utc_str).astimezone(gettz(tz_str)).strftime(format)


def get_date_time_delta(delta):
    return str(datetime.now().replace(tzinfo=gettz('UTC')) + timedelta(delta))


def get_date_age(date):
    return (datetime.now(tz=tzutc()) - parser.parse(date)).days


def format_struct(evt):
    return json.dumps(evt, indent=2, ensure_ascii=False)


def get_resource_tag_value(resource, k):
    for t in resource.get('Tags', []):
        if t['Key'] == k:
            return t['Value']
    return ''


def strip_prefix(value, prefix):
    if value.startswith(prefix):
        return value[len(prefix):]
    return value


def resource_format(resource, resource_type):
    if resource_type.startswith('aws.'):
        resource_type = strip_prefix(resource_type, 'aws.')
    if resource_type == 'ec2':
        tag_map = {t['Key']: t['Value'] for t in resource.get('Tags', ())}
        return "%s %s %s %s %s %s" % (
            resource['InstanceId'],
            resource.get('VpcId', 'NO VPC!'),
            resource['InstanceType'],
            resource.get('LaunchTime'),
            tag_map.get('Name', ''),
            resource.get('PrivateIpAddress'))
    elif resource_type == 'ami':
        return "%s %s %s" % (
            resource.get('Name'), resource['ImageId'], resource['CreationDate'])
    elif resource_type == 'sagemaker-notebook':
        return "%s" % (resource['NotebookInstanceName'])
    elif resource_type == 's3':
        return "%s" % (resource['Name'])
    elif resource_type == 'ebs':
        return "%s %s %s %s" % (
            resource['VolumeId'],
            resource['Size'],
            resource['State'],
            resource['CreateTime'])
    elif resource_type == 'rds':
        return "%s %s %s %s" % (
            resource['DBInstanceIdentifier'],
            "%s-%s" % (
                resource['Engine'], resource['EngineVersion']),
            resource['DBInstanceClass'],
            resource['AllocatedStorage'])
    elif resource_type == 'asg':
        tag_map = {t['Key']: t['Value'] for t in resource.get('Tags', ())}
        return "%s %s %s" % (
            resource['AutoScalingGroupName'],
            tag_map.get('Name', ''),
            "instances: %d" % (len(resource.get('Instances', []))))
    elif resource_type == 'elb':
        tag_map = {t['Key']: t['Value'] for t in resource.get('Tags', ())}
        if 'ProhibitedPolicies' in resource:
            return "%s %s %s %s" % (
                resource['LoadBalancerName'],
                "instances: %d" % len(resource['Instances']),
                "zones: %d" % len(resource['AvailabilityZones']),
                "prohibited_policies: %s" % ','.join(
                    resource['ProhibitedPolicies']))
        return "%s %s %s" % (
            resource['LoadBalancerName'],
            "instances: %d" % len(resource['Instances']),
            "zones: %d" % len(resource['AvailabilityZones']))
    elif resource_type == 'redshift':
        return "%s %s %s" % (
            resource['ClusterIdentifier'],
            'nodes:%d' % len(resource['ClusterNodes']),
            'encrypted:%s' % resource['Encrypted'])
    elif resource_type == 'emr':
        return "%s status:%s" % (
            resource['Id'],
            resource['Status']['State'])
    elif resource_type == 'cfn':
        return "%s" % (
            resource['StackName'])
    elif resource_type == 'launch-config':
        return "%s" % (
            resource['LaunchConfigurationName'])
    elif resource_type == 'security-group':
        name = resource.get('GroupName', '')
        for t in resource.get('Tags', ()):
            if t['Key'] == 'Name':
                name = t['Value']
        return "%s %s %s inrules: %d outrules: %d" % (
            name,
            resource['GroupId'],
            resource.get('VpcId', 'na'),
            len(resource.get('IpPermissions', ())),
            len(resource.get('IpPermissionsEgress', ())))
    elif resource_type == 'log-group':
        if 'lastWrite' in resource:
            return "name: %s last_write: %s" % (
                resource['logGroupName'],
                resource['lastWrite'])
        return "name: %s" % (resource['logGroupName'])
    elif resource_type == 'cache-cluster':
        return "name: %s created: %s status: %s" % (
            resource['CacheClusterId'],
            resource['CacheClusterCreateTime'],
            resource['CacheClusterStatus'])
    elif resource_type == 'cache-snapshot':
        cid = resource.get('CacheClusterId')
        if cid is None:
            cid = ', '.join([
                ns['CacheClusterId'] for ns in resource['NodeSnapshots']])
        return "name: %s cluster: %s source: %s" % (
            resource['SnapshotName'],
            cid,
            resource['SnapshotSource'])
    elif resource_type == 'redshift-snapshot':
        return "name: %s db: %s" % (
            resource['SnapshotIdentifier'],
            resource['DBName'])
    elif resource_type == 'ebs-snapshot':
        return "name: %s date: %s" % (
            resource['SnapshotId'],
            resource['StartTime'])
    elif resource_type == 'subnet':
        return "%s %s %s %s %s %s" % (
            resource['SubnetId'],
            resource['VpcId'],
            resource['AvailabilityZone'],
            resource['State'],
            resource['CidrBlock'],
            resource['AvailableIpAddressCount'])
    elif resource_type == 'account':
        return " %s %s" % (
            resource['account_id'],
            resource['account_name'])
    elif resource_type == 'cloudtrail':
        return "%s" % (
            resource['Name'])
    elif resource_type == 'vpc':
        return "%s " % (
            resource['VpcId'])
    elif resource_type == 'iam-group':
        return " %s %s %s" % (
            resource['GroupName'],
            resource['Arn'],
            resource['CreateDate'])
    elif resource_type == 'rds-snapshot':
        return " %s %s %s" % (
            resource['DBSnapshotIdentifier'],
            resource['DBInstanceIdentifier'],
            resource['SnapshotCreateTime'])
    elif resource_type == 'iam-user':
        return " %s " % (
            resource['UserName'])
    elif resource_type == 'iam-role':
        return " %s %s " % (
            resource['RoleName'],
            resource['CreateDate'])
    elif resource_type == 'iam-policy':
        return " %s " % (
            resource['PolicyName'])
    elif resource_type == 'iam-profile':
        return " %s " % (
            resource['InstanceProfileId'])
    elif resource_type == 'dynamodb-table':
        return "name: %s created: %s status: %s" % (
            resource['TableName'],
            resource['CreationDateTime'],
            resource['TableStatus'])
    elif resource_type == "sqs":
        return "QueueURL: %s QueueArn: %s " % (
            resource['QueueUrl'],
            resource['QueueArn'])
    elif resource_type == "efs":
        return "name: %s  id: %s  state: %s" % (
            resource['Name'],
            resource['FileSystemId'],
            resource['LifeCycleState']
        )
    elif resource_type == "network-addr":
        return "ip: %s  id: %s  scope: %s" % (
            resource['PublicIp'],
            resource['AllocationId'],
            resource['Domain']
        )
    elif resource_type == "route-table":
        return "id: %s  vpc: %s" % (
            resource['RouteTableId'],
            resource['VpcId']
        )
    elif resource_type == "app-elb":
        return "arn: %s  zones: %s  scheme: %s" % (
            resource['LoadBalancerArn'],
            len(resource['AvailabilityZones']),
            resource['Scheme'])
    elif resource_type == "nat-gateway":
        return "id: %s  state: %s  vpc: %s" % (
            resource['NatGatewayId'],
            resource['State'],
            resource['VpcId'])
    elif resource_type == "internet-gateway":
        return "id: %s  attachments: %s" % (
            resource['InternetGatewayId'],
            len(resource['Attachments']))
    elif resource_type == 'lambda':
        return "Name: %s  RunTime: %s  \n" % (
            resource['FunctionName'],
            resource['Runtime'])
    else:
        return "%s" % format_struct(resource)


def get_provider(mailer_config):
    if mailer_config.get('queue_url', '').startswith('asq://'):
        return Providers.Azure

    return Providers.AWS


def kms_decrypt(config, logger, session, encrypted_field):
    if config.get(encrypted_field):
        try:
            kms = session.client('kms')
            return kms.decrypt(
                CiphertextBlob=base64.b64decode(config[encrypted_field]))[
                    'Plaintext'].decode('utf8')
        except (TypeError, base64.binascii.Error) as e:
            logger.warning(
                "Error: %s Unable to base64 decode %s, will assume plaintext." %
                (e, encrypted_field))
        except ClientError as e:
            if e.response['Error']['Code'] != 'InvalidCiphertextException':
                raise
            logger.warning(
                "Error: %s Unable to decrypt %s with kms, will assume plaintext." %
                (e, encrypted_field))
        return config[encrypted_field]
    else:
        logger.debug("No encrypted value to decrypt.")
        return None


def decrypt(config, logger, session, encrypted_field):
    if config.get(encrypted_field):
        provider = get_provider(config)
        if provider == Providers.Azure:
            from c7n_mailer.azure_mailer.utils import azure_decrypt
            return azure_decrypt(config, logger, session, encrypted_field)
        elif provider == Providers.AWS:
            return kms_decrypt(config, logger, session, encrypted_field)
        else:
            raise Exception("Unknown provider")
    else:
        logger.debug("No encrypted value to decrypt.")
        return None


# https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-user-identity.html
def get_aws_username_from_event(logger, event):
    if event is None:
        return None
    identity = event.get('detail', {}).get('userIdentity', {})
    if not identity:
        logger.warning("Could not get recipient from event \n %s" % (
            format_struct(event)))
        return None
    if identity['type'] == 'AssumedRole':
        logger.debug(
            'In some cases there is no ldap uid is associated with AssumedRole: %s',
            identity['arn'])
        logger.debug(
            'We will try to assume that identity is in the AssumedRoleSessionName')
        user = identity['arn'].rsplit('/', 1)[-1]
        if user is None or user.startswith('i-') or user.startswith('awslambda'):
            return None
        if ':' in user:
            user = user.split(':', 1)[-1]
        return user
    if identity['type'] == 'IAMUser' or identity['type'] == 'WebIdentityUser':
        return identity['userName']
    if identity['type'] == 'Root':
        return None
    # this conditional is left here as a last resort, it should
    # be better documented with an example UserIdentity json
    if ':' in identity['principalId']:
        user_id = identity['principalId'].split(':', 1)[-1]
    else:
        user_id = identity['principalId']
    return user_id
