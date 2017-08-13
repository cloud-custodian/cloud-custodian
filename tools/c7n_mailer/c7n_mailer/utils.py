# Copyright 2015-2017 Capital One Services, LLC
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
import datetime
import jinja2
import json
import os
import yaml

from io import StringIO
from dateutil import parser
from dateutil.tz import gettz


def get_jinja_env():
    env = jinja2.Environment(trim_blocks=True, autoescape=False)
    env.filters['yaml_safe'] = yaml.safe_dump
    env.filters['date_time_format'] = date_time_format
    env.filters['get_date_time_delta'] = get_date_time_delta
    env.globals['format_resource'] = resource_format
    env.globals['format_struct'] = format_struct
    env.loader  = jinja2.FileSystemLoader(
        [
            os.path.abspath(
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    '..',
                    'msg-templates')), os.path.abspath('/')
        ]
    )
    return env


def get_rendered_jinja(target, sqs_message, resources, logger):
    env = get_jinja_env()
    mail_template = sqs_message['action'].get('template')
    if not os.path.isabs(mail_template):
        mail_template = '%s.j2' % mail_template
    try:
        template = env.get_template(mail_template)
    except Exception as error_msg:
        logger.error("Invalid template reference %s\n%s" % (mail_template, error_msg))
        return
    rendered_jinja = template.render(
        recipient=target,
        resources=resources,
        account=sqs_message.get('account', ''),
        event=sqs_message.get('event', None),
        action=sqs_message['action'],
        policy=sqs_message['policy'],
        region=sqs_message.get('region', ''))
    return rendered_jinja


# eg, target_tag_keys could be resource-owners ['Owners', 'SupportTeam']
# and this function would go through the resource and look for any tag keys
# that match Owners or SupportTeam, and return those values as targets
def get_resource_tag_targets(resource, target_tag_keys):
    if 'Tags' not in resource:
        return []
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
        region=sqs_message.get('region', '')
    )
    return subject


def setup_defaults(config):
    config.setdefault('region', 'us-east-1')
    config.setdefault('ses_region', config.get('region'))
    config.setdefault('memory', 1024)
    config.setdefault('timeout', 300)
    config.setdefault('subnets', None)
    config.setdefault('security_groups', None)
    config.setdefault('contact_tags', [])
    config.setdefault('ldap_uri', None)
    config.setdefault('ldap_bind_dn', None)
    config.setdefault('ldap_bind_user', None)
    config.setdefault('ldap_bind_password', None)


def date_time_format(utc_str, tz_str='US/Eastern', format='%Y %b %d %H:%M %Z'):
    return parser.parse(utc_str).astimezone(gettz(tz_str)).strftime(format)


def get_date_time_delta(delta):
    return str(datetime.datetime.now().replace(tzinfo=gettz('UTC')) + datetime.timedelta(delta))


def format_struct(evt):
    buf = StringIO()
    json.dump(evt, buf, indent=2)
    return buf.getvalue()


def resource_tag(resource, k):
    for t in resource.get('Tags', []):
        if t['Key'] == k:
            return t['Value']
    return ''


def resource_format(resource, resource_type):
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
            resource['Name'], resource['ImageId'], resource['CreationDate'])
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
        return "name: %s cluster: %s source: %s" % (
            resource['SnapshotName'],
            resource['CacheClusterId'],
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
    else:
        print("Unknown resource type", resource_type)
        return "%s" % format_struct(resource)
