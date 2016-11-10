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
from email.utils import parseaddr
from functools import partial
import json
import logging
import os
import time
import zlib

from boto3 import Session
import jinja2

from address import get_user
from record import resource_tag, resource_owner, resource_format, format_struct


log = logging.getLogger('custodian.mail')


class Processor(object):
    """
    Cases

     - set of resources from poll policy, email individual owner
     - set of resources from poll policy, email tag value
     - set of resources from poll policy, send to sns/explicit address
     - set of resources from push policy, email event owner
     - set of resources from push policy, send to sns/explicit address
    """

    def __init__(self, config, session, cache):
        self.config = config
        self.ses = session.client('ses')
        self.sts = session.client('sts')
        self.sns_cache = {}
        self.cache = cache
        self.env = jinja2.Environment(
            trim_blocks=True, autoescape=False)

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

    def flush(self):
        # TODO batch messages till this is called.
        pass

    def process_data_message(self, message):
        data = json.loads(zlib.decompress(base64.b64decode(message['Body'])))
        log.info("Got account:%s message:%s %s:%d policy:%s recipients:%s" % (
            data.get('account', 'na'),
            message['MessageId'],
            data['policy']['resource'],
            len(data['resources']),
            data['policy']['name'],
            ', '.join(data['action']['to'])))

        targets = set(data['action']['to'])
        resource_targets = []
        if 'resource-owner' in targets:
            targets.remove('resource-owner')
            self.send_resource_owner_messages(data)
        if 'event-owner' in targets:
            targets.remove('event-owner')
            recipient = resolve_recipient_from_event(data['event'])
            if recipient is not None:
                targets.add(recipient)
        if not targets:
            log.info("No intended targets found for message")
            return
        self.send_resource_set_message(targets, data, data['resources'])

    def send_resource_owner_messages(self, data):
        owners = {}
        for r in data['resources']:
            owner = self.find_resource_owner(r)
            if owner is None:
                log.info("No resource owner found for %s" % (
                    resource_format(r, data['policy']['resource'])))
                continue
            owners.setdefault(owner, []).append(r)

        # Address resolution can take some time, try to do it upfront
        t = time.time()
        owner_addrs = {
            o: (self.resolve_address(o) or o) for o in owners.keys()}
        log.info("policy:%s resolved %d owners in %0.2f seconds" % (
            data['policy']['name'], len(owner_addrs), time.time() - t))

        # TODO, check deadline and requeue before sending any messages.
        for o, resources in owners.items():
            self.send_resource_set_message([owner_addrs[o]], data, resources)

    def find_resource_owner(self, resource):
        if 'Tags' not in resource:
            return
        tags = {t['Key']: t['Value'] for t in resource['Tags']}
        for t in self.OwnerTags:
            if t in tags:
                return tags[t]

    def send_resource_set_message(self, targets, data, resources):
        for t in targets:
            addr = self.resolve_address(t)
            if addr is None:
                log.warning("Could not resolve address %s" % t)
                continue
            msg = self.render(addr, data, resources)
            if not msg:
                continue
            subject = data['action'].get(
                'subject',
                'Custodian notification - %s' % (data['policy']['name']))

            tmpl = jinja2.Template(subject)
            subject = tmpl.render(
                account=data.get('account', ''),
                region=data.get('region', ''))
            if addr.startswith('arn'):
                # Max length of subject in sns is 100 chars
                if len(subject) > 100:
                    subject = subject[:97] + '..'
                try:
                    self.deliver_sns(addr, subject, msg, data)
                except Exception as e:
                    log.warning(
                        "Error policy:%s account:%s sending sns to %s \n %s" % (
                            data['policy'], data.get('account', 'na'), addr, e))
                continue

            name, email_addr = parseaddr(addr)
            if not email_addr:
                log.info("Invalid email address %s", addr)
                continue

            log.info("Sending account:%s policy:%s email:%s to %s" % (
                data.get('account', ''),
                data['policy']['name'],
                data['action'].get('template', 'default'),
                email_addr))

            format = data['action'].get(
                'template', 'default').endswith('html') and 'Html' or 'Text'

            from_addr = data['action'].get('from', self.config['from_address'])

            params = {
                'Source': from_addr,
                'Destination': {
                    'ToAddresses': [email_addr]},
                'Message': {
                    'Subject': {
                        'Data': subject,
                        'Charset': 'utf-8'},
                    'Body': {format: {
                        'Data': msg,
                        'Charset': 'utf-8'}}}}

            cc_addrs = data['action'].get('cc', None)
            if cc_addrs:
                params['Destination']['CcAddresses'] = cc_addrs
            try:
                self.ses.send_email(**params)
            except Exception as e:
                log.warning(
                    "Error policy:%s account:%s sending to:%s \n %s" % (
                        data['policy'], data.get('account', ''), addr, e))

    def deliver_sns(self, topic, subject, msg, data):
        account = topic.split(':')[4]
        if account in self.sns_cache:
            sns = self.sns_cache[account]
        else:
            if account not in self.config['cross_accounts']:
                log.error(
                    "No cross account role for sending sns to %s" % topic)
                return
            creds = self.sts.assume_role(
                RoleArn=self.config['cross_accounts'][account],
                RoleSessionName="CustodianNotification")['Credentials']
            session = Session(
                aws_access_key_id=creds['AccessKeyId'],
                aws_secret_access_key=creds['SecretAccessKey'],
                aws_session_token=creds['SessionToken'])
            self.sns_cache[account] = sns = session.client('sns')

        log.info("Sending account:%s policy:%s sns:%s to %s" % (
            data.get('account', ''),
            data['policy']['name'],
            data['action'].get('template', 'default'),
            topic))
        sns.publish(TopicArn=topic, Subject=subject, Message=msg)

    def render(self, target, data, resources):
        try:
            template = self.env.get_template("%s.j2" % (
                data['action'].get('template', 'default')))
        except jinja2.TemplateNotFound:
            log.error("Invalid template reference %s.j2" % (
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
                recipient = resolve_recipient_from_event(data['event'])
                if recipient:
                    targets.append(recipient)
            elif e.startswith('sns'):
                targets.append(e)
            elif '@' in e:
                targets.append(e)
            else:
                log.warning('unknown target %s' % e)
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


def resolve_recipient_from_event(event):
    if event is None:
        return None
    identity = event.get('detail', {}).get('userIdentity', {})
    if not identity:
        log.warning("Could not get recipient from event \n %s" % (
            format_struct(event)))
        return None

    if identity['type'] == 'Root':
        return None

    if ':' in identity['principalId']:
        user_id = identity['principalId'].split(':', 1)[-1]
    else:
        user_id = identity['principalId']
    return user_id
