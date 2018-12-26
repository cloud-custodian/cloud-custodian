import json
import hashlib
from six.moves.urllib.parse import urlparse

from c7n.exception import PolicyExecutionError, PolicyValidationError
from c7n.utils import local_session, type_schema
from .core import MethodAction


class PostFinding(MethodAction):
    """Post finding for matched resources to Cloud Security Command Center.
    """
    schema = type_schema(
        'post-finding',
        **{
            'source': {'type': 'string',
                       'description': 'qualified name of source to post to CSCC as'},
            'org-domain': {'type': 'string'},
            'org-id': {'type': 'integer'},
            'category': {'type': 'string'},
            'marks': {
                'type': 'object',
                'patternProperties': {'^*': {'type': 'string'}},
                'additionalProperties': False}})

    method_spec = {'op': 'create', 'result': 'name', 'annotation_key': 'c7n:Finding'}
    CustodianSourceName = 'CloudCustodian'
    Service = 'securitycenter'
    ServiceVersion = 'v1beta1'

    _source = None

    def validate(self):
        if not any([self.data.get(k) for k in ('source', 'org-domain', 'org-id')]):
            raise PolicyValidationError(
                "policy:%s CSCC post-finding requires one of source, org-domain, org-id" % (
                    self.manager.ctx.policy.name))

    def process(self, resources):
        self.initialize_source()
        return super(PostFinding, self).process(resources)

    def get_client(self, session, model):
        session.client(self.Service, self.Version, 'organizations.sources.findings')

    def get_resource_params(self, model, resource):
        return self.get_finding(resource)

    def initialize_source(self):
        # Ideally we'll be given a source, but we'll attempt to auto create it
        # if given an org_domain or org_id.
        if 'source' in self.data:
            self._source = self.data['source']

        session = local_session(self.manager.session_factory)

        # Resolve Organization Id
        if 'org-id' in self.data:
            org_id = self.data['org-id']
        else:
            orgs = session.client('cloudresourcemanager', 'v1', 'organizations')
            res = orgs.execute_query(
                'search', {'domain': self.data['org-domain']}).get('organizations')
            if not res:
                raise PolicyExecutionError("Could not determine organization id")
            org_id = res[0]['name'].rsplit('/', 1)[-1]

        # Resolve Source
        client = session.client(self.Service, self.ServiceVersion, 'organizations.sources')
        source = None
        res = [s for s in
               client.execute_query(
                   'list', {'name': 'organizations/{}'.format(org_id)}).get('sources')
               if s['name'] == self.CustodianSourceName]
        if res:
            source = res[0]['name']

        if source is None:
            source = client.execute('create', {
                'displayName': 'CloudCustodian',
                'description': 'Cloud Management Rules Engine',
                'parent': 'organizations/{}'.format(org_id)}).get('name')

        self.log.info(
            "Resolved source: %s, please update policy with this source value" % source)
        self._source = source

    def get_name(self, r):
        """Given an arbitrary resource attempt to resolve back to a qualified name."""
        # common with compute and older apis
        if 'selfLink' in r:
            u = urlparse(r['selfLink'])
            return "//{}/{}".format(u.netloc, u.path)
        if 'name' in r and '/' in r['name']:
            return "//{}.googleapis.com/{}/{}" % (
                self.manager.resource_type.service,
                self.manager.resource_type.version,
                r['name'])
        raise ValueError("resource-type:%s cant fetch name" % self.manager.type)

    def get_finding(self, resource):
        policy = self.manager.ctx.policy
        resource_name = self.get_name(resource)

        id_gen = hashlib.shake_256(policy.name.encode('utf8'))
        id_gen.update(resource_name.encode('utf8'))
        finding_id = id_gen.hexdigest(32)

        finding = {
            'name': '{}/findings/{}'.format(
                self._source, finding_id),
            'parent': self._source,
            'resource_name': resource_name,
            'state': 'ACTIVE',
            'category': self.data.get('category'),
            'event_time': self.manager.ctx.start_time,
            'source_properties': {
                'resource-type': self.manager.resource_type,
                'title': policy.title,
                'policy-name': policy.name,
                'policy': json.dumps(policy.data)
            }
        }

        return finding
