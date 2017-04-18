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
import base64
import jinja2
import json
import os
import smtplib
import time
import yaml
import zlib

from address import get_user
from boto3 import Session
from email.mime.text import MIMEText
from email.utils import parseaddr
from functools import partial
from record import date_time_format, format_struct
from record import resource_format, resource_owner, resource_tag


class SqsMessageProcessor(object):
    """
    Cases

     - set of resources from poll policy, email individual owner
     - set of resources from poll policy, email tag value
     - set of resources from poll policy, send to sns/explicit address
     - set of resources from push policy, email event owner
     - set of resources from push policy, send to sns/explicit address
    """

    def __init__(self, config, session, cache, logger):
        self.config    = config
        self.logger    = logger
        self.aws_ses   = session.client('ses', region_name=config.get('ses_region'))
        self.aws_sts   = session.client('sts')
        self.sns_cache = {}
        self.cache     = cache
        self.env       = jinja2.Environment(
            trim_blocks=True, autoescape=False)
        self.env.filters['yaml_safe'] = yaml.safe_dump
        self.env.filters['date_time_format'] = date_time_format

        self.env.globals['format_resource'] = resource_format
        self.env.globals['format_struct'] = format_struct
        self.env.globals['resource_tag'] = resource_tag
        self.env.globals['resource_owner'] = resource_owner

        self.OwnerTags = config['contact_tags']
        self.get_user = partial(
            get_user,
            ldap_uri=config['ldap_uri'],
            base_dn=config['ldap_bind_dn'],
            ldap_bind_user=config['ldap_bind_user'],
            ldap_bind_password=config['ldap_bind_password'])

        self.env.loader = jinja2.FileSystemLoader(
            os.path.abspath(
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    '..',
                    'msg-templates')))

    def get_priority_header(self, message):
        message_contents = json.loads(zlib.decompress(base64.b64decode(message['Body'])))
        if 'priority_header' in message_contents['action']:
            return message_contents['action']['priority_header']
        return None

    def priority_header_is_valid(self, priority_header):
        try:
            priority_header_int = int(priority_header)
        except:
            priority_header_int = None
        if priority_header_int and 0 < int(priority_header_int) < 6:
            return True
        else:
            self.logger.warning('mailer priority_header is not a valid string from 1 to 5')
            return False

    def process_sqs_messsage(self, message):
        data = json.loads(zlib.decompress(base64.b64decode(message['Body'])))

        self.logger.info("Got account:%s message:%s %s:%d policy:%s recipients:%s" % (
            data.get('account', 'na'),
            message['MessageId'],
            data['policy']['resource'],
            len(data['resources']),
            data['policy']['name'],
            ', '.join(data['action']['to'])))

        targets = set(data['action']['to'])
        if 'resource-owner' in targets:
            targets.remove('resource-owner')
            self.send_resource_owner_messages(data)
        if 'event-owner' in targets:
            targets.remove('event-owner')
            recipient = self.get_aws_username_from_event(data['event'])
            if recipient is not None:
                targets.add(recipient)
        if not targets:
            self.logger.info("No intended targets found for message")
            return
        self.send_message_to_targets(targets, data, data['resources'])

    def send_resource_owner_messages(self, data):
        owners = {}
        for r in data['resources']:
            contact_tags = self.find_resource_owners(r)
            if not contact_tags:
                self.logger.info("No resource owner found for %s" % (
                    resource_format(r, data['policy']['resource'])))
                continue
            for contact_tag in contact_tags:
                owners.setdefault(contact_tag, []).append(r)

        # Address resolution can take some time, try to do it upfront
        t = time.time()
        owner_addrs = {
            o: (self.resolve_address(o) or o) for o in owners.keys()}
        self.logger.info("policy:%s resolved %d owners in %0.2f seconds" % (
            data['policy']['name'], len(owner_addrs), time.time() - t))

        # TODO, check deadline and requeue before sending any messages.
        for o, resources in owners.items():
            self.send_message_to_targets([owner_addrs[o]], data, resources)

    def find_resource_owners(self, resource):
        if 'Tags' not in resource:
            return []
        tags = {t['Key']: t['Value'] for t in resource['Tags']}
        owners = []
        for t in self.OwnerTags:
            if t in tags:
                owners.append(tags[t])
        return owners

    def target_is_sns(self, target):
        if target.startswith('arn'):
            return True
        return False

    def send_message_to_targets(self, targets, data, resources):
        for target in targets:
            to_addr = self.resolve_address(target)
            if to_addr is None:
                self.logger.warning("Could not resolve address %s" % target)
                continue
            body = self.render(to_addr, data, resources)
            if not body:
                continue
            subject = data['action'].get(
                'subject',
                'Custodian notification - %s' % (data['policy']['name']))

            tmpl = jinja2.Template(subject)
            subject = tmpl.render(
                account=data.get('account', ''),
                region=data.get('region', ''))
            if self.target_is_sns(to_addr):
                self.deliver_sns(to_addr, subject, body, data)
                continue

            name, email_to_addr = parseaddr(to_addr)
            if not email_to_addr:
                self.logger.info("Invalid email address %s", to_addr)
                continue
            self.send_c7n_email(data, email_to_addr, subject, body)

    def send_c7n_email(self, data, email_to_addr, subject, body):
        email_format = data['action'].get(
            'template', 'default').endswith('html') and 'Html' or 'Text'

        from_addr          = data['action'].get('from', self.config['from_address'])
        message            = MIMEText(body.encode('utf-8'), email_format)
        message['From']    = from_addr
        message['To']      = email_to_addr
        message['Subject'] = subject
        priority_header    = data['action'].get('priority_header', None)
        if priority_header and self.priority_header_is_valid(data['action']['priority_header']):
            message['X-Priority'] = '1'
        cc_addrs = data['action'].get('cc', [])
        if cc_addrs:
            message['cc'] = cc_addrs
        try:
            # if smtp_server is set in mailer.yml, send through smtp
            smtp_server = self.config.get('smtp_server')
            if smtp_server:
                smtp_port = int(self.config.get('smtp_port', 25))
                smtp_ssl  = bool(self.config.get('smtp_ssl', True))
                smtp_connection = smtplib.SMTP(smtp_server, smtp_port)
                if smtp_ssl:
                    smtp_connection.starttls()
                    smtp_connection.ehlo()
                if self.config.get('smtp_username') or self.config.get('smtp_password'):
                    smtp_username = self.config.get('smtp_username')
                    smtp_password = self.config.get('smtp_password')
                    smtp_connection.login(smtp_username, smtp_password)
                all_to_addresses = cc_addrs + [email_to_addr]
                smtp_connection.sendmail(from_addr, all_to_addresses, message.as_string())
                smtp_connection.quit()
            # if smtp_server isn't set in mailer.yml, use aws ses normally.
            else:
                self.aws_ses.send_raw_email(RawMessage={'Data': message.as_string()})
        except Exception as e:
            self.logger.warning(
                "Error policy:%s account:%s sending to:%s \n\n error: %s\n\n mailer.yml: %s" % (
                    data['policy'], data.get('account', ''), email_to_addr, e, self.config))
        self.logger.info("Sending account:%s policy:%s email:%s to %s" % (
            data.get('account', ''),
            data['policy']['name'],
            data['action'].get('template', 'default'),
            email_to_addr))

    def deliver_sns(self, topic, subject, msg, data):
        # Max length of subject in sns is 100 chars
        if len(subject) > 100:
            subject = subject[:97] + '..'
        try:
            account = topic.split(':')[4]
            if account in self.sns_cache:
                sns = self.sns_cache[account]
            else:
                if account not in self.config['cross_accounts']:
                    self.logger.error(
                        "No cross account role for sending sns to %s" % topic)
                    return
                creds = self.aws_sts.assume_role(
                    RoleArn=self.config['cross_accounts'][account],
                    RoleSessionName="CustodianNotification")['Credentials']
                session = Session(
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken'])
                self.sns_cache[account] = sns = session.client('sns')

            self.logger.info("Sending account:%s policy:%s sns:%s to %s" % (
                data.get('account', ''),
                data['policy']['name'],
                data['action'].get('template', 'default'),
                topic))
            sns.publish(TopicArn=topic, Subject=subject, Message=msg)
        except Exception as e:
            self.logger.warning(
                "Error policy:%s account:%s sending sns to %s \n %s" % (
                    data['policy'], data.get('account', 'na'), topic, e))

    def render(self, target, data, resources):
        try:
            template = self.env.get_template("%s.j2" % (
                data['action'].get('template', 'default')))
        except jinja2.TemplateNotFound:
            self.logger.error("Invalid template reference %s.j2" % (
                data['action'].get('template', 'default')))
            return

        message = template.render(
            recipient=target,
            resources=resources,
            account=data.get('account', ''),
            event=data.get('event', None),
            action=data['action'],
            policy=data['policy'],
            region=data.get('region', ''))

        return message

    def get_policy_targets(self, data):
        notify_action = data['action']
        targets = []
        for e in notify_action['to']:
            if e == 'resource-owner':
                targets.append('resource-owner')
            elif e == 'event-owner' and data['event']:
                recipient = self.get_aws_username_from_event(data['event'])
                if recipient:
                    targets.append(recipient)
            elif e.startswith('sns'):
                targets.append(e)
            elif '@' in e:
                targets.append(e)
            else:
                self.logger.warning('unknown target %s' % e)
        return targets

    def resolve_address(self, addr):
        # This whole method is goo.

        if '-' in addr:
            tower, taddr = addr.split('-', 1)
            if len(taddr) == 6:
                addr = taddr
        if '@' in addr and '.' in addr:
            return addr
        elif addr.startswith('arn'):
            return addr

        elif len(addr) == 6:
            if self.cache:
                email = self.cache.get(addr)
                if email:
                    return email
            info = self.get_user(
                addr,
                # Need to refactor this code to get manager cc working
                manager=False)

            if info is None:
                return None

            # Cache to reduce burden on ldap, and don't cache fallback
            if self.cache and not info['mail'].startswith(addr):
                self.cache.set(addr, info['mail'])

            return info['mail']
        else:
            return None

    def get_aws_username_from_event(self, event):
        if event is None:
            return None
        identity = event.get('detail', {}).get('userIdentity', {})
        if not identity:
            self.logger.warning("Could not get recipient from event \n %s" % (
                format_struct(event)))
            return None

        if identity['type'] == 'Root':
            return None

        if ':' in identity['principalId']:
            user_id = identity['principalId'].split(':', 1)[-1]
        else:
            user_id = identity['principalId']
        return user_id
