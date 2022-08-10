# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
import json
import hashlib
from urllib.parse import urlparse

from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n.utils import local_session, type_schema
from .core import MethodAction

from c7n_gcp.provider import resources as gcp_resources

SEVERITIES = ['LOW', 'MEDIUM', 'HIGH', 'SEVERITY_UNSPECIFIED']


class PostFinding(MethodAction):
    """Post finding for matched resources to Cloud Security Command Center.


    :Example:

    .. code-block:: yaml

       policies:
         - name: gcp-instances-with-label
           resource: gcp.instance
           filters:
             - "tag:name": "bad-instance"
           actions:
             - type: post-finding
               org-domain: example.io
               category: MEDIUM_INTERNET_SECURITY

    The source for custodian can either be specified inline to the policy, or
    custodian can generate one at runtime if it doesn't exist given a org-domain
    or org-id.

    Finding updates are not currently supported, due to upstream api issues.
    """
    schema = type_schema(
        'post-finding',
        **{
            'source': {
                'type': 'string',
                'description': 'qualified name of source to post to CSCC as'},
            'org-domain': {'type': 'string'},
            'org-id': {'type': 'integer'},
            'category': {'type': 'string'},
            'severity': {'type': 'string', 'enum': SEVERITIES}})
    schema_alias = True
    method_spec = {'op': 'create', 'result': 'name', 'annotation_key': 'c7n:Finding'}

    # create throws error if already exists, patch method has bad docs.
    ignore_error_codes = (409,)

    CustodianSourceName = 'CloudCustodian'
    DefaultCategory = 'Custodian'
    DefaultSeverity = 'SEVERITY_UNSPECIFIED'
    Service = 'securitycenter'
    ServiceVersion = 'v1'

    _source = None

    # security center permission model is pretty obtuse to correct
    permissions = (
        'securitycenter.findings.list',
        'securitycenter.findings.update',
        'resourcemanager.organizations.get',
        'securitycenter.assetsecuritymarks.update',
        'securitycenter.sources.update',
        'securitycenter.sources.list'
    )

    def validate(self):
        if not any([self.data.get(k) for k in ('source', 'org-domain', 'org-id')]):
            raise PolicyValidationError(
                "policy:%s CSCC post-finding requires one of source, org-domain, org-id" % (
                    self.manager.ctx.policy.name))

    def process(self, resources):
        self.initialize_source()
        return super(PostFinding, self).process(resources)

    def get_client(self, session, model):
        return session.client(
            self.Service, self.ServiceVersion, 'organizations.sources.findings')

    def get_resource_params(self, model, resource):
        return self.get_finding(resource)

    def initialize_source(self):
        # Ideally we'll be given a source, but we'll attempt to auto create it
        # if given an org_domain or org_id.
        if self._source:
            return self._source
        elif 'source' in self.data:
            self._source = self.data['source']
            return self._source

        session = local_session(self.manager.session_factory)

        # Resolve Organization Id
        if 'org-id' in self.data:
            org_id = self.data['org-id']
        else:
            orgs = session.client('cloudresourcemanager', 'v1', 'organizations')
            res = orgs.execute_query(
                'search', {'body': {
                    'filter': 'domain:%s' % self.data['org-domain']}}).get(
                        'organizations')
            if not res:
                raise PolicyExecutionError("Could not determine organization id")
            org_id = res[0]['name'].rsplit('/', 1)[-1]

        # Resolve Source
        client = session.client(self.Service, self.ServiceVersion, 'organizations.sources')
        source = None
        res = [s for s in
               client.execute_query(
                   'list', {'parent': 'organizations/{}'.format(org_id)}).get('sources')
               if s['displayName'] == self.CustodianSourceName]
        if res:
            source = res[0]['name']

        if source is None:
            source = client.execute_command(
                'create',
                {'parent': 'organizations/{}'.format(org_id),
                 'body': {
                     'displayName': self.CustodianSourceName,
                     'description': 'Cloud Management Rules Engine'}}).get('name')
        self.log.info(
            "policy:%s resolved cscc source: %s, update policy with this source value",
            self.manager.ctx.policy.name,
            source)
        self._source = source
        return self._source

    def get_name(self, r):
        """Given an arbitrary resource attempt to resolve back to a qualified name."""
        namer = ResourceNameAdapters[self.manager.resource_type.service]
        return namer(r)

    def get_finding(self, resource):
        policy = self.manager.ctx.policy
        resource_name = self.get_name(resource)
        # ideally we could be using shake, but its py3.6+ only
        finding_id = hashlib.sha256(
            b"%s%s" % (
                policy.name.encode('utf8'),
                resource_name.encode('utf8'))).hexdigest()[:32]

        finding = {
            'name': '{}/findings/{}'.format(self._source, finding_id),
            'resourceName': resource_name,
            'state': 'ACTIVE',
            'category': self.data.get('category', self.DefaultCategory),
            'severity': self.data.get('severity', self.DefaultSeverity),
            'eventTime': datetime.datetime.utcnow().isoformat('T') + 'Z',
            'sourceProperties': {
                'resource_type': self.manager.type,
                'title': policy.data.get('title', policy.name),
                'policy_name': policy.name,
                'policy': json.dumps(policy.data)
            }
        }

        request = {
            'parent': self._source,
            'findingId': finding_id[:31],
            'body': finding}
        return request

    @classmethod
    def register_resource(klass, registry, resource_class):
        if resource_class.resource_type.service not in ResourceNameAdapters:
            return
        if 'post-finding' in resource_class.action_registry:
            return
        resource_class.action_registry.register('post-finding', klass)


# CSCC uses its own notion of resource id, if we want our findings on
# a resource to be linked from the asset view we need to post w/ the
# same resource name. If this conceptulization of resource name is
# standard, then we should move these to resource types with
# appropriate hierarchies by service.


def name_compute(r):
    prefix = urlparse(r['selfLink']).path.strip('/').split('/')[2:][:-1]
    return "//compute.googleapis.com/{}/{}".format(
        "/".join(prefix),
        r['id'])


def name_iam(r):
    return "//iam.googleapis.com/projects/{}/serviceAccounts/{}".format(
        r['projectId'],
        r['uniqueId'])


def name_resourcemanager(r):
    rid = r.get('projectNumber')
    if rid is not None:
        rtype = 'projects'
    else:
        rid = r.get('organizationId')
        rtype = 'organizations'
    return "//cloudresourcemanager.googleapis.com/{}/{}".format(
        rtype, rid)


def name_container(r):
    return "//container.googleapis.com/{}".format(
        "/".join(urlparse(r['selfLink']).path.strip('/').split('/')[1:]))


def name_storage(r):
    return "//storage.googleapis.com/{}".format(r['name'])


def name_appengine(r):
    return "//appengine.googleapis.com/{}".format(r['name'])


ResourceNameAdapters = {
    'appengine': name_appengine,
    'cloudresourcemanager': name_resourcemanager,
    'compute': name_compute,
    'container': name_container,
    'iam': name_iam,
    'storage': name_storage,
}

gcp_resources.subscribe(PostFinding.register_resource)
