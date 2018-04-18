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
from __future__ import absolute_import, division, print_function, unicode_literals

import jinja2
import os
from ruamel import yaml

from dateutil import parser
from dateutil.tz import gettz, tzutc
from datetime import datetime, timedelta

from c7n import utils


def get_jinja_env():
    env = jinja2.Environment(trim_blocks=True, autoescape=False)
    env.filters['yaml_safe'] = yaml.safe_dump
    env.filters['date_time_format'] = date_time_format
    env.filters['get_date_time_delta'] = get_date_time_delta
    env.filters['get_date_age'] = get_date_age
    env.globals['format_resource'] = utils.resource_format
    env.globals['format_struct'] = utils.format_struct
    env.globals['get_resource_tag_value'] = get_resource_tag_value
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
        account_id=sqs_message.get('account_id', ''),
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
        account_id=sqs_message.get('account_id', ''),
        region=sqs_message.get('region', '')
    )
    return subject


def setup_defaults(config):
    config.setdefault('region', 'us-east-1')
    config.setdefault('ses_region', config.get('region'))
    config.setdefault('memory', 1024)
    config.setdefault('runtime', 'python2.7')
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
    return str(datetime.now().replace(tzinfo=gettz('UTC')) + timedelta(delta))

def get_date_age(date):
    return (datetime.now(tz=tzutc()) - parser.parse(date)).days


def get_resource_tag_value(resource, k):
    for t in resource.get('Tags', []):
        if t['Key'] == k:
            return t['Value']
    return ''


