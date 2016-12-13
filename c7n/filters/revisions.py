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
"""
Custodian support for diffing and patching across multiple versions
of a resource.
"""
import json
import zlib

from botocore.exceptions import ClientError
from botocore.parsers import BaseJSONParser

from c7n.filters import Filter
from c7n.utils import local_session, type_schema, camelResource, get_retry


ErrNotFound = "ResourceNotDiscoveredException"


class Diff(Filter):
    """Compute the diff from the current resource to a previous version.

    A resource matches the filter if a diff exists between the current
    resource and the selected revision.

    Utilizes config as a resource revision database.
    """

    schema = type_schema(
        'diff',
        selector={'enum': ['previous', 'date', 'locked']},
        # For date selectors allow value specification
        selector_value={'type': 'string'})

    selector_value = mode = parser = resource_shape = None

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)
        config = session.client('config')

        self.model = self.manager.get_model()
        self.parser = ConfigResourceParser()
        self.resource_shape = self.get_resource_shape(session)

        results = []
        for r in resources:
            revisions = self.get_revisions(session, config, r)
            r['c7n:previous-revision'] = rev = self.select_revision(revisions)
            delta = self.diff(r, rev)
            if delta:
                r['c7n:diff'] = delta
                results.append(r)
        return r

    def get_revisions(self, config, resource):
        config = session.client('config')
        params = {
            resourceType: self.model.config_type,
            resourceId: res[self.model.id]}
        params.update(self.get_selector_params(resource))
        try:
            revisions = config.get_resource_config_history(
                **params)['configurationItems']
        except ClientError as e:
            if e.response['Error']['Code'] != ErrNotFound:
                self.log.debug(
                    "config - resource %s:%s not found" % (
                        model.config_type, res[model.id]))
                revisions = []
            raise
        return revisions

    def get_selector_params(self, resource):
        params = {}
        selector = self.data.get('selector', 'previous')
        if selector == 'date':
            if not self.selector_value:
                self.selector_value = parse_date(
                    self.data.get('selector_value'))
            params['laterTime'] = self.selector_value
            params['limit'] = 3
        elif selector == 'previous':
            params['limit'] = 2
        elif selector == 'locked':
            params['laterTime'] = resource.get('c7n:locked_date')
            params['limit'] = 2
        return params

    def select_revision(self, resource, revisions, selector):
        for rev in revisions:
            return parser.parse(
                camelResource(json.loads(rev['configuration'])),
                resource_shape)

    def diff(self, source, target):
        differ = SecurityGroupDiff()
        return differ.diff(source, target)

    def get_resource_shape(self, session):
        resource_model = self.manager.get_model()
        service = session.client(resource_model.service)
        shape_name = resource_model.config_type.split('::')[-1]
        return service.meta.service_model.shape_for(shape_name)


class ConfigResourceParser(BaseJSONParser):

    def parse(self, data, shape):
        return self._do_parse(data, shape)

    def _do_parse(self, data, shape):
        return self._parse_shape(shape, data)


class SecurityGroupDiff(object):
    """Diff two versions of a security group

    Immutable: GroupId, GroupName, Description, VpcId, OwnerId
    Mutable: Tags, Rules
    """

    def diff(self, source, target):
        delta = {}
        tag_delta = self.get_tag_delta(source, target)
        if tag_delta:
            delta['tags'] = tag_delta
        ingress_delta = self.get_rule_delta('IpPermissions', source, target)
        if ingress_delta:
            delta['ingress'] = ingress_delta
        egress_delta = self.get_rule_delta(
            'IpPermissionsEgress', source, target)
        if egress_delta:
            delta['egress'] = egress_delta
        if delta:
            return delta

    def get_tag_delta(self, source, target):
        source_tags = {t['Key']: t['Value'] for t in source['Tags']}
        target_tags = {t['Key']: t['Value'] for t in target['Tags']}
        target_keys = set(target_tags.keys())
        source_keys = set(source_tags.keys())
        removed = source_keys.difference(target_keys)
        added = target_keys.difference(source_keys)
        changed = set()
        for k in target_keys.intersection(source_keys):
            if source_tags[k] != target_tags[k]:
                changed.add(k)
        return {k: v for k, v in {
            'added': {k: target_tags[k] for k in added},
            'removed': {k: source_tags[k] for k in removed},
            'updated': {k: target_tags[k] for k in changed}}.items() if v}

    def get_rule_delta(self, key, source, target):
        source_rules = {
            self.compute_rule_hash(r): r for r in source.get(key, ())}
        target_rules = {
            self.compute_rule_hash(r): r for r in target.get(key, ())}
        source_keys = set(source_rules.keys())
        target_keys = set(target_rules.keys())
        removed = source_keys.difference(target_keys)
        added = target_keys.difference(source_keys)
        return {k: v for k, v in
                {'removed': [source_rules[rid] for rid in removed],
                'added': [target_rules[rid] for rid in added]}.items() if v}

    RULE_ATTRS = (
        ('PrefixListIds', 'PrefixListId'),
        ('UserIdGroupPairs', 'GroupId'),
        ('IpRanges', 'CidrIp'),
        ('Ipv6Ranges', 'CidrIpv6')
    )

    def compute_rule_hash(self, rule):
        buf = "%d-%d-%s-" % (
            rule.get('FromPort', 0),
            rule.get('ToPort', 0),
            rule.get('IpProtocol', '-1')
            )
        for a, ke in self.RULE_ATTRS:
            ev = [e[ke] for e in rule[a]]
            ev.sort()
            for e in ev:
                buf += "%s-" % e
        return abs(zlib.crc32(buf))


class SecurityGroupPatch(object):

    RULE_TYPE_MAP = {
        'egress': ('IpPermissionsEgress',
                   'revoke_security_group_egress',
                   'authorize_security_group_egress'),
        'ingress': ('IpPermissions',
                    'revoke_security_group_ingress',
                    'authorize_security_group_ingress')}

    retry = staticmethod(get_retry((
        'RequestLimitExceeded', 'Client.RequestLimitExceeded')))

    def apply_delta(self, client, target, change_set):
        if 'tags' in change_set:
            self.process_tags(client, target, change_set['tags'])
        if 'ingress' in change_set:
            self.process_rules(
                client, 'ingress', target, change_set['ingress'])
        if 'egress' in change_set:
            self.process_rules(
                client, 'egress', target, change_set['egress'])

    def process_tags(self, client, group, tag_delta):
        if 'removed' in tag_delta:
            self.retry(client.delete_tags,
                       Resources=[group['GroupId']],
                       Tags=[{'Key': k}
                             for k in tag_delta['removed']])
        tags = []
        if 'added' in tag_delta:
            tags.extend(
                [{'Key': k, 'Value': v}
                 for k, v in tag_delta['added'].items()])
        if 'updated' in tag_delta:
            tags.extend(
                [{'Key': k, 'Value': v}
                 for k, v in tag_delta['updated'].items()])
        self.retry(client.create_tags, Resources=[group['GroupId']], Tags=tags)

    def process_rules(self, client, rule_type, group, delta):
        key, revoke_op, auth_op = self.RULE_TYPE_MAP[rule_type]
        revoke, authorize = getattr(
            client, revoke_op), getattr(client, auth_op)

        # Process removes
        self.retry(revoke, GroupId=group['GroupId'],
                   IpPermissions=[r for r in delta['removed']])

        # Process adds
        self.retry(authorize, GroupId=group['GroupId'],
                   IpPermissions=[r for r in delta['added']])


# TODO List

Action = object


class Locked(Filter):
    """Has the resource been locked."""
    schema = type_schema(
        'locked',
        value={'type': 'boolean'},
        api_endpoint={'type': 'string'})


class Lock(Action):
    """Lock a resource from further modifications.

    Get current revision of given object. We may have an inflight
    snapshotDelivery coming.
    """
    schema = type_schema('lock')


class Unlock(Action):
    """Unlock a resource for further modifications."""


class Revert(Action):
    """Restore a resource to a previous version."""

