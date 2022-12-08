# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import calendar
import datetime
import json
import logging

import boto3
from dateutil.tz import tzutc

from c7n.credentials import assumed_session
from c7n.ctx import ExecutionContext
from c7n.handler import Config
from c7n.manager import resources

from db import LockDb
from errors import AccountNotFound, UnknownResourceType, ResourceNotFound
from utils import Encoder

UTC = tzutc()

log = logging.getLogger('sphere11.controller')


class Controller:

    supported_resources = set(('security-group', 'vpc'))

    def __init__(self, config):
        self.config = config
        self.account_sessions = {}
        self.resource_managers = {}

        self.db = LockDb(
            boto3.Session(),
            config['db']['lock_table'],
            config['db'].get('endpoint'))

    def get_session(self, account_id):
        """Get an active session in the target account."""
        if account_id not in self.account_sessions:
            if account_id not in self.config['accounts']:
                raise AccountNotFound("account:%s is unknown" % account_id)

            self.account_sessions[account_id] = s = assumed_session(
                self.config['accounts'][account_id]['role'], "Sphere11")
            s._session.user_agent_name = "Sphere11"
            s._session.user_agent_version = "0.07"
        return self.account_sessions[account_id]

    def get_resource_manager(self, session, region, resource_id, policy=None):
        def session_factory(assume=False, region=None):
            if region:
                session.set_config_variable('region', region)
            return session
        ctx = ExecutionContext(
            session_factory, Config({"name": "sphere11"}),
            Config.empty(verbose=True))
        cls = self.get_resource_class(resource_id)
        return cls(ctx, policy and policy or {})

    def get_resource_class(self, resource_id):
        for rname, rmgr in resources.items():
            if rname not in self.supported_resources:
                continue
            m = rmgr.get_model()
            id_prefix = getattr(m, 'id_prefix', None)
            if id_prefix is None:
                continue
            if resource_id.startswith(id_prefix):
                return rmgr
        raise UnknownResourceType(
            "resource:%s not a supported resource type" % resource_id)

    def get_resource_parent_id(self, resource_id, resource):
        return resource['VpcId']

    def get_account_delta(
            self, account_id, region, endpoint,
            resource_types=(('sg-', 'security-group'),)):
        session = self.get_session(account_id)
        delta = {}
        records = self.db.iter_resources(account_id)
        for rid, rtype in resource_types:
            method = getattr(
                self, 'get_account_%s_delta' % (rtype.replace('-', '_')))
            delta[rtype] = method(
                session, region, rid,
                records=[r for r in records
                         if r['ResourceId'].startswith(rid)],
                endpoint=endpoint,
                role=self.config['accounts'][account_id].get(
                    'invoke-api-role'))
        return delta

    def get_account_security_group_delta(
            self, session, region, rid, records, endpoint, role):
        manager = self.get_resource_manager(
            session, region, rid,
            policy={'filters': [
                {'or': [
                    {'type': 'value',
                     'key': 'GroupId',
                     'op': 'in',
                     'value': [g['ResourceId'] for g in records
                               if g['ResourceId'].startswith('sg-') and
                               g.get('LockStatus', '') == 'locked']},
                    {'type': 'value',
                     'key': 'VpcId',
                     'op': 'in',
                     'value': [g['ResourceId'] for g in records
                               if g['ResourceId'].startswith('vpc-') and
                               g.get('LockStatus', '') == 'locked']},
                ]},
                {'type': 'locked',
                 'endpoint': endpoint,
                 'role': role},
                {'type': 'diff', 'selector': 'locked'}]})
        return manager.resources()

    def get_resource_delta(self, account_id, resource_id, region):
        session = self.get_session(account_id)
        manager = self.get_resource_manager(
            session, region, resource_id,
            policy={'filters': [{'type': 'diff', 'selector': 'previous'}]})

        results = manager.get_resources([resource_id], False)
        if not results:
            raise ResourceNotFound(
                "account:%s resource:%s in region:%s was not found" % (
                    account_id, resource_id, region))
        resource = results[0]
        filtered = manager.filter_resources([resource])
        return resource, bool(
            filtered or not resource.get('c7n:previous-revision'))

    def lock(self, account_id, resource_id, region):
        resource, delta = self.get_resource_delta(
            account_id, resource_id, region)
        #  parent_id = self.get_resource_parent_id(resource_id, resource)

        # The most recent config revision is not current, waiting..
        if delta:
            lock_status = self.db.STATE_PENDING
        else:
            lock_status = self.db.STATE_LOCKED
            revision = resource['c7n:previous-revision']
            # increment one second, as we use this as latesttime for revision
            # when querying
            revision_date = calendar.timegm(revision['date'].timetuple()) + 1

        record = dict(
            AccountId=account_id,
            ResourceId=resource_id,
            #  ParentId=parent_id,
            #  Region=region,
            LockDate=calendar.timegm(datetime.datetime.utcnow().timetuple()),
            LockStatus=lock_status)
        if not delta:
            record['RevisionDate'] = revision_date
        self.db.save(record)

        topic = self.config['accounts'][account_id].get('notify-locks')
        if topic:
            self.get_session(account_id).client('sns').publish(
                TopicArn=topic,
                Message=json.dumps(record, indent=2, cls=Encoder))
        return record

    def unlock(self, account_id, resource_id):
        record = dict(
            AccountId=account_id,
            ResourceId=resource_id,
            LockDate=calendar.timegm(datetime.datetime.utcnow().timetuple()),
            LockStatus=self.db.STATE_UNLOCKED)
        self.db.save(record)
        topic = self.config['accounts'][account_id].get('notify-locks')
        if topic:
            self.get_session(account_id).client('sns').publish(
                TopicArn=topic,
                Message=json.dumps(record, indent=2, cls=Encoder))
        return record

    def info(self, account_id, resource_id, parent_id):
        record = self.db.info(account_id, resource_id, parent_id)
        return record

    def process_pending(self):
        # TODO: we need to fork out to ourselves as we grow accounts
        # under management.
        # TODO: separate out record processing from account.
        for account_id in self.config['accounts'].keys():
            pending = self.db.iter_pending(account_id)
            if not pending:
                continue

            session = self.get_session(account_id)
            config = session.client('config')
            topic = self.config['accounts'][account_id].get('notify-locks')
            if topic:
                sns = session.client('sns')

            for p in pending:
                m = self.get_resource_class(p['ResourceId']).get_model()
                n = datetime.datetime.utcfromtimestamp(p['LockDate']).replace(
                    tzinfo=UTC)
                config_items = config.get_resource_config_history(
                    resourceId=p['ResourceId'],
                    earlierTime=n,
                    resourceType=m.config_type,
                    limit=1).get('configurationItems', ())

                log.info("processing pending %s %s found:%d" % (
                    p['ResourceId'], n, bool(config_items)))

                if not config_items:
                    continue

                revision = config_items.pop()
                revision_date = calendar.timegm(
                    revision['configurationItemCaptureTime'].timetuple())
                p['RevisionDate'] = revision_date
                p['LockStatus'] = 'locked'

                # Track this to ensure sla
                delay = p['RevisionDate'] - p['LockDate']
                p['LockDelay'] = delay

                self.db.save(p)

                log.info("locked pending %s %s delay:%d" % (
                    p['ResourceId'], n, float(delay)))

                if topic:
                    sns.publish(
                        TopicArn=topic, Message=json.dumps(p, cls=Encoder))
