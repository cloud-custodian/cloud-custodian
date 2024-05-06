# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import itertools
from c7n_gcp.filters.iampolicy import IamPolicyFilter

from c7n_gcp.actions import SetIamPolicy, MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo

from c7n.resolver import ValuesFrom
from c7n.utils import type_schema, local_session
from c7n.filters.core import ValueFilter, ListItemFilter
from c7n.filters.missing import Missing

from googleapiclient.errors import HttpError


@resources.register('organization')
class Organization(QueryResourceManager):
    """GCP resource: https://cloud.google.com/resource-manager/reference/rest/v1/organizations
    """
    class resource_type(TypeInfo):
        service = 'cloudresourcemanager'
        version = 'v1'
        component = 'organizations'
        scope = 'global'
        enum_spec = ('search', 'organizations[]', {'body': {}})
        id = 'name'
        name = 'displayName'
        default_report_fields = [
            "name", "displayName", "creationTime", "lifecycleState"]
        asset_type = "cloudresourcemanager.googleapis.com/Organization"
        scc_type = "google.cloud.resourcemanager.Organization"
        perm_service = 'resourcemanager'
        permissions = ('resourcemanager.organizations.get',)
        urn_component = "organization"
        urn_id_segments = (-1,)  # Just use the last segment of the id in the URN
        urn_has_project = False

        @staticmethod
        def get(client, resource_info):
            org = resource_info['resourceName'].rsplit('/', 1)[-1]
            return client.execute_query(
                'get', {'name': "organizations/" + org})


@Organization.action_registry.register('set-iam-policy')
class OrganizationSetIamPolicy(SetIamPolicy):
    """
    Overrides the base implementation to process Organization resources correctly.
    """
    def _verb_arguments(self, resource):
        verb_arguments = SetIamPolicy._verb_arguments(self, resource)
        verb_arguments['body'] = {}
        return verb_arguments


@resources.register('folder')
class Folder(QueryResourceManager):
    """GCP resource: https://cloud.google.com/resource-manager/reference/rest/v1/folders
    """
    class resource_type(TypeInfo):
        service = 'cloudresourcemanager'
        version = 'v2'
        component = 'folders'
        scope = 'global'
        enum_spec = ('list', 'folders', None)
        name = id = 'name'
        default_report_fields = [
            "name", "displayName", "lifecycleState", "createTime", "parent"]
        asset_type = "cloudresourcemanager.googleapis.com/Folder"
        perm_service = 'resourcemanager'
        urn_component = "folder"
        urn_id_segments = (-1,)  # Just use the last segment of the id in the URN
        urn_has_project = False

    def get_resources(self, resource_ids):
        client = self.get_client()
        results = []
        for rid in resource_ids:
            if not rid.startswith('folders/'):
                rid = 'folders/%s' % rid
            results.append(client.execute_query('get', {'name': rid}))
        return results

    def get_resource_query(self):
        if 'query' in self.data:
            for child in self.data.get('query'):
                if 'parent' in child:
                    return {'parent': child['parent']}


@resources.register('project')
class Project(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/projects
    """
    class resource_type(TypeInfo):
        service = 'cloudresourcemanager'
        version = 'v1'
        component = 'projects'
        scope = 'global'
        enum_spec = ('list', 'projects', None)
        name = id = 'projectId'
        default_report_fields = [
            "name", "lifecycleState", "createTime", "parent.id"]
        asset_type = "cloudresourcemanager.googleapis.com/Project"
        scc_type = "google.cloud.resourcemanager.Project"
        perm_service = 'resourcemanager'
        labels = True
        labels_op = 'update'
        urn_component = "project"
        urn_has_project = False

        @staticmethod
        def get_label_params(resource, labels):
            return {'projectId': resource['projectId'],
                    'body': {
                        'name': resource['name'],
                        'parent': resource['parent'],
                        'labels': labels}}

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'projectId': resource_info['resourceName'].rsplit('/', 1)[-1]})

    def get_resource_query(self):
        # https://cloud.google.com/resource-manager/reference/rest/v1/projects/list
        if 'query' in self.data:
            for child in self.data.get('query'):
                if 'filter' in child:
                    return {'filter': child['filter']}


Project.filter_registry.register('missing', Missing)


@Project.filter_registry.register('iam-policy')
class ProjectIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process Project resources correctly.
    """
    permissions = ('resourcemanager.projects.getIamPolicy',)

    def _verb_arguments(self, resource):
        verb_arguments = SetIamPolicy._verb_arguments(self, resource)
        verb_arguments['body'] = {}
        return verb_arguments


@Project.filter_registry.register('compute-meta')
class ProjectComputeMetaFilter(ValueFilter):
    """
    Allows filtering on project-level compute metadata including common instance metadata
    and quotas.

    :example:

    Find Projects that have not enabled OS Login for compute instances

    .. code-block:: yaml

        policies:
          - name: project-compute-os-login-not-enabled
            resource: gcp.project
            filters:
              - type: compute-meta
                key: "commonInstanceMetadata.items[?key==`enable-oslogin`].value | [0]"
                op: ne
                value_type: normalize
                value: true

    """

    key = 'c7n:projectComputeMeta'
    permissions = ('compute.projects.get',)
    schema = type_schema('compute-meta', rinherit=ValueFilter.schema)

    def __call__(self, resource):
        if self.key in resource:
            return resource[self.key]

        session = local_session(self.manager.session_factory)
        self.client = session.client('compute', 'v1', 'projects')

        resource[self.key] = self.client.execute_command('get', {"project": resource['projectId']})

        return super().__call__(resource[self.key])


@Project.action_registry.register('delete')
class ProjectDelete(MethodAction):
    """Delete a GCP Project

    Note this will also schedule deletion of assets contained within
    the project. The project will not be accessible, and assets
    contained within the project may continue to accrue costs within
    a 30 day period. For details see
    https://cloud.google.com/resource-manager/docs/creating-managing-projects#shutting_down_projects

    """
    method_spec = {'op': 'delete'}
    attr_filter = ('lifecycleState', ('ACTIVE',))
    schema = type_schema('delete')

    def get_resource_params(self, model, resource):
        return {'projectId': resource['projectId']}


@Project.action_registry.register('set-iam-policy')
class ProjectSetIamPolicy(SetIamPolicy):
    """
    Overrides the base implementation to process Project resources correctly.
    """
    def _verb_arguments(self, resource):
        verb_arguments = SetIamPolicy._verb_arguments(self, resource)
        verb_arguments['body'] = {}
        return verb_arguments


class HierarchyAction(MethodAction):

    def load_hierarchy(self, resources):
        parents = {}
        session = local_session(self.manager.session_factory)

        for r in resources:
            client = self.get_client(session, self.manager.resource_type)
            ancestors = client.execute_command(
                'getAncestry', {'projectId': r['projectId']}).get('ancestor')
            parents[r['projectId']] = [
                a['resourceId']['id'] for a in ancestors
                if a['resourceId']['type'] == 'folder']
        self.parents = parents
        self.folder_ids = set(itertools.chain(*self.parents.values()))

    def load_folders(self):
        folder_manager = self.manager.get_resource_manager('gcp.folder')
        self.folders = {
            f['name'].split('/', 1)[-1]: f for f in
            folder_manager.get_resources(list(self.folder_ids))}

    def load_metadata(self):
        raise NotImplementedError()

    def diff(self, resources):
        raise NotImplementedError()

    def process(self, resources):
        if self.attr_filter:
            resources = self.filter_resources(resources)

        self.load_hierarchy(resources)
        self.load_metadata()
        op_set = self.diff(resources)
        client = self.manager.get_client()
        for op in op_set:
            self.invoke_api(client, *op)


@Project.action_registry.register('propagate-labels')
class ProjectPropagateLabels(HierarchyAction):
    """Propagate labels from the organization hierarchy to a project.

    folder-labels should resolve to a json data mapping of folder path
    to labels that should be applied to contained projects.

    as a worked example assume the following resource hierarchy

    ::

      - /dev
           /network
              /project-a
           /ml
              /project-b

    Given a folder-labels json with contents like

    .. code-block:: json

      {"dev": {"env": "dev", "owner": "dev"},
       "dev/network": {"owner": "network"},
       "dev/ml": {"owner": "ml"}

    Running the following policy

    .. code-block:: yaml

      policies:
       - name: tag-projects
         resource: gcp.project
         # use a server side filter to only look at projects
         # under the /dev folder the id for the dev folder needs
         # to be manually resolved outside of the policy.
         query:
           - filter: "parent.id:389734459211 parent.type:folder"
         filters:
           - "tag:owner": absent
         actions:
           - type: propagate-labels
             folder-labels:
                url: file://folder-labels.json

    Will result in project-a being tagged with owner: network and env: dev
    and project-b being tagged with owner: ml and env: dev

    """
    schema = type_schema(
        'propagate-labels',
        required=('folder-labels',),
        **{
            'folder-labels': {
                '$ref': '#/definitions/filters_common/value_from'}},
    )

    attr_filter = ('lifecycleState', ('ACTIVE',))
    permissions = ('resourcemanager.folders.get',
                   'resourcemanager.projects.update')
    method_spec = {'op': 'update'}

    def load_metadata(self):
        """Load hierarchy tags"""
        self.resolver = ValuesFrom(self.data['folder-labels'], self.manager)
        self.labels = self.resolver.get_values()
        self.load_folders()
        self.resolve_paths()

    def resolve_paths(self):
        self.folder_paths = {}

        def get_path_segments(fid):
            p = self.folders[fid]['parent']
            if p.startswith('folder'):
                for s in get_path_segments(p.split('/')[-1]):
                    yield s
            yield self.folders[fid]['displayName']

        for fid in self.folder_ids:
            self.folder_paths[fid] = '/'.join(get_path_segments(fid))

    def resolve_labels(self, project_id):
        hlabels = {}
        parents = self.parents[project_id]
        for p in reversed(parents):
            pkeys = [p, self.folder_paths[p], 'folders/%s' % p]
            for pk in pkeys:
                hlabels.update(self.labels.get(pk, {}))

        return hlabels

    def diff(self, resources):
        model = self.manager.resource_type

        for r in resources:
            hlabels = self.resolve_labels(r['projectId'])
            if not hlabels:
                continue

            delta = False
            rlabels = r.get('labels', {})
            for k, v in hlabels.items():
                if k not in rlabels or rlabels[k] != v:
                    delta = True
            if not delta:
                continue

            rlabels = dict(rlabels)
            rlabels.update(hlabels)

            if delta:
                yield ('update', model.get_label_params(r, rlabels))


@Organization.filter_registry.register('essential-contacts')
class OrgContactsFilter(ListItemFilter):
    """Filter Resources based on essential contacts configuration

    .. code-block:: yaml

      - name: org-essential-contacts
        resource: gcp.organization
        filters:
        - type: essential-contacts
          count: 2
          count_op: gte
          attrs:
            - validationState: VALID
            - type: value
              key: notificationCategorySubscriptions
              value: TECHNICAL
              op: contains
    """
    schema = type_schema(
        'essential-contacts',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    annotate_items = True
    permissions = ("essentialcontacts.contacts.list",)

    def get_item_values(self, resource):
        session = local_session(self.manager.session_factory)
        client = session.client("essentialcontacts", "v1", "organizations.contacts")
        pages = client.execute_paged_query('list', {'parent': resource['name'], 'pageSize': 100})
        contacts = []
        for page in pages:
            contacts.extend(page.get('contacts', []))
        return contacts


@Organization.filter_registry.register('org-policy')
class OrgPoliciesFilter(ListItemFilter):
    """Filter Resources based on orgpolicy configuration

    .. code-block:: yaml

      - name: org-policy
        resource: gcp.organization
        filters:
        - type: org-policy
          attrs:
            - type: value
              key: constraint
              value: constraints/iam.allowedPolicyMemberDomains
              op: contains
    """
    schema = type_schema(
        'org-policy',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'}
    )

    annotate_items = True
    permissions = ("orgpolicy.policy.get",)

    def get_item_values(self, resource):
        session = local_session(self.manager.session_factory)
        client = session.client("cloudresourcemanager", "v1", "organizations")
        pages = client.execute_paged_query('listOrgPolicies', {'resource': resource['name']})
        policies = []
        for page in pages:
            policies.extend(page.get('policies', []))
        return policies


@Project.filter_registry.register('access-approval')
class AccessApprovalFilter(ValueFilter):
    """Filter Resources based on access approval configuration

    .. code-block:: yaml

      - name: project-access-approval
        resource: gcp.project
        filters:
        - type: access-approval
          key: enrolledServices.cloudProduct
          value: "all"
    """
    schema = type_schema('access-approval', rinherit=ValueFilter.schema)
    permissions = ('accessapproval.settings.get',)

    def process(self, resources, event=None):
        return [r for r in resources
                if self.match(self.get_access_approval(r))]

    def get_access_approval(self, resource):
        session = local_session(self.manager.session_factory)
        client = session.client("accessapproval", "v1", "projects")
        project = resource['projectId']

        try:
            access_approval = client.execute_command(
                'getAccessApprovalSettings',
                {'name': f"projects/{project}/accessApprovalSettings"},)
        except HttpError as ex:
            if (ex.status_code == 400
                and ex.reason == "Precondition check failed.") \
                    or (ex.status_code == 404):
                # For above exceptions, it implies that access approval is
                # not enabled, so we return an empty setting.
                access_approval = {}
            else:
                raise ex

        return access_approval


@Organization.filter_registry.register('iam-policy')
class OrganizationIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process Organization resources correctly.
    """
    permissions = ('resourcemanager.organizations.getIamPolicy',)

    def _verb_arguments(self, resource):
        verb_arguments = SetIamPolicy._verb_arguments(self, resource)
        verb_arguments['body'] = {}
        return verb_arguments


@Folder.filter_registry.register('iam-policy')
class FolderIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process Folder resources correctly.
    """
    permissions = ('resourcemanager.folders.getIamPolicy',)

    def _verb_arguments(self, resource):
        verb_arguments = SetIamPolicy._verb_arguments(self, resource)
        verb_arguments['body'] = {}
        return verb_arguments
