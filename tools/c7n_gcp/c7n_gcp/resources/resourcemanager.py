# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import itertools
from tools.c7n_gcp.c7n_gcp.filters.iampolicy import IamPolicyFilter

from c7n_gcp.actions import SetIamPolicy, MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import (
    AssetInventory, DescribeSource, QueryResourceManager, TypeInfo)

from c7n.resolver import ValuesFrom
from c7n.utils import type_schema, local_session


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


class FolderInventory(AssetInventory):

    def _describe_format(self, resources):
        for r in resources:
            # check for cached resources
            if not self._common_describe_format(r):
                continue
            # remap only valid for v2 folders, v3 switches to 'state'
            r['lifecycleState'] = r.pop('state')

        return resources


@resources.register('folder')
class Folder(QueryResourceManager):
    """GCP resource: https://cloud.google.com/resource-manager/reference/rest/v2/folders
    """
    class resource_type(TypeInfo):
        service = 'cloudresourcemanager'
        version = 'v2'
        component = 'folders'
        scope = 'global'
        enum_spec = ('search', 'folders', None)
        name = id = 'name'
        default_report_fields = [
            "name", "displayName", "lifecycleState", "createTime", "parent"]
        asset_type = "cloudresourcemanager.googleapis.com/Folder"
        asset_history = False  # supported but its loses info
        perm_service = 'resourcemanager'
        permissions = ('resourcemanager.folders.get',)

    source_mapping = {'inventory': FolderInventory, 'describe-gcp': DescribeSource}

    def get_resource_query(self):
        if 'query' in self.data:
            for child in self.data.get('query'):
                if 'parent' in child:
                    return {'body': {"query": "parent=%s" % child['parent']}}
                if 'scope' in child:
                    return {'scope': child['scope']}


class ProjectSource:

    def get_resources(self, query):
        if query and 'subtree' in query:
            return self.get_sub_tree(query)
        return super().get_resources(query)


class ProjectInventoryHierarchy(ProjectSource, AssetInventory):
    # for inventory we filter hierarchy client side as this is much faster
    # for deeply nested trees as there is enough metadata from inventory
    # to just to do a set intersection for hierarchy.

    def _describe_format(self, resources):
        for r in resources:
            # check if operating on cached resources
            if not self._common_describe_format(r):
                continue
            # only while project resource is using v1 of resourcemanager api
            r['lifecycleState'] = r.pop('state')
            r['name'] = r.pop('displayName', None)
            attrs = r.pop('additionalAttributes', None)
            if attrs:
                r.update(attrs)
            # can obsolete as we move to v3 of resourcemanager api
            if isinstance(r['parent'], str):
                ptype, pname = r['parent'].split('/', 2)
                r['parent'] = {'type': ptype[:-1], 'id': pname}
        return resources

    def _filter_resource_parent(self, resources, parent):
        return [r for r in resources if parent in r.get('folders', ())]

    def get_sub_tree(self, query):
        # get a second resource manager so we can cache the results sans the subtree query cache key
        prm = self.manager.get_resource_manager('gcp.project')
        projects = prm.resources()
        return self._filter_resource_parent(projects, query['subtree'])


class ProjectDescribeHierarchy(ProjectSource, DescribeSource):
    """Describe Source for Projects for working against a folder subtree"""

    def get_resources(self, query):
        if query and 'subtree' in query:
            return self.get_sub_tree(query)
        return super().get_resources(query)

    def get_sub_tree(self, query):
        frm = self.manager.get_resource_manager('gcp.folder')
        folder_ids = self.get_child_folders(frm, query['subtree'], set())
        folder_ids.add(query['subtree'])

        # now for each folder fetch the projects
        prm = self.manager.get_resource_manager('gcp.project')
        projects = []
        for fid in folder_ids:
            prm.data = self.get_project_query(fid)
            projects.extend(prm.resources())
        return projects

    def get_project_query(self, folder_id):
        return {'query': [{
            'filter': 'parent.type:folder parent.id:%s' % folder_id.split('/', 1)[-1]}]}

    def get_subfolder_query(self, folder_id):
        return {'query': [{'parent': folder_id}]}

    def get_child_folders(self, frm, folder_id, result_ids):
        frm.data = self.get_subfolder_query(folder_id)
        for folder in frm.resources():
            result_ids.add(folder['name'])
            self.get_child_folders(frm, folder['name'], result_ids)
        return result_ids


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
            "name", "displayName", "lifecycleState", "createTime", "parent"]
        asset_type = "cloudresourcemanager.googleapis.com/Project"
        asset_history = False
        scc_type = "google.cloud.resourcemanager.Project"
        perm_service = 'resourcemanager'
        labels = True
        labels_op = 'update'

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

    source_mapping = {
        'describe-gcp': ProjectDescribeHierarchy,
        'inventory': ProjectInventoryHierarchy
    }

    def get_resource_query(self):
        # https://cloud.google.com/resource-manager/reference/rest/v1/projects/list
        q = {}
        for child in self.data.get('query', ()):
            if 'filter' in child:
                q['filter'] = child['filter']
            if 'subtree' in child:
                q['subtree'] = child['subtree']
            if self.source_type == 'inventory' and 'scope' in child:
                q['scope'] = child['scope']
        return q or None


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
        root_parent = self.data.get('root-parent')
        if root_parent and root_parent.startswith('folders'):
            root_parent = root_parent.split('/')[-1]

        for r in resources:
            client = self.get_client(session, self.manager.resource_type)
            if 'folders' in r:
                parents[r['projectId']] = [
                    f.split('/', 1)[-1] for f in r['folders']]
            else:
                ancestors = client.execute_command(
                    'getAncestry', {'projectId': r['projectId']}).get('ancestor')
                parents[r['projectId']] = [
                    a['resourceId']['id'] for a in ancestors
                    if a['resourceId']['type'] == 'folder']

            if root_parent and root_parent in parents[r['projectId']]:
                rparents = parents[r['projectId']]
                parents[r['projectId']] = rparents[:rparents.index(root_parent) + 1]
        self.parents = parents
        self.folder_ids = set(itertools.chain(*self.parents.values()))

    def load_folders(self):
        folder_manager = self.manager.get_resource_manager('gcp.folder')
        if folder_manager.source_type == 'inventory':
            folders = [r for r in folder_manager.resources()
                       if r['name'].split('/', 1)[-1] in self.folder_ids]
        else:
            folders = self._get_folders(folder_manager, self.folder_ids)
        self.folders = {
            f['name'].split('/', 1)[-1]: f for f in folders}

    def _get_folders(self, folder_manager, folder_ids):
        client = folder_manager.get_client()
        results = []
        for rid in folder_ids:
            if not rid.startswith('folders/'):
                rid = 'folders/%s' % rid
            results.append(client.execute_query('get', {'name': rid}))
        return results

    def load_metadata(self):
        raise NotImplementedError()

    def diff(self, resources):
        raise NotImplementedError()

    def process(self, resources):
        if self.attr_filter:
            resources = self.filter_resources(resources)
        if not resources:
            return

        self.load_hierarchy(resources)
        self.load_metadata()
        op_set = self.diff(resources)
        client = self.manager.get_client()
        count = 0
        for op in op_set:
            self.invoke_api(client, *op)
            count += 1
        if count:
            self.log.info('propagate labels updated %d projects', count)


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

    Note you can also use folder ids in the form "folders/33311281122" in
    your label json file, ie.

    .. code-block:: json

      {"folders/123333333": {"env": "dev", "owner": "dev"},
       "network/shared": {"env": "qa"},
       "folders/333344444": {"owner": "network"}}


    when applying to a subtree the folder json can also be specified relative
    to a root parent. ie. given a tree, where we only want to apply folder
    labels to the projects under network.

    ::

       /dev - folders/123333333
           /network - folders/333344444
              /shared
                /project-a
              /team-a
                /project-b
              /team-b
                /project-c
           /ml
           ...

    you can specify a policy like

    .. code-block:: yaml

      policies:
       - name: tag-projects-inventory
         resource: gcp.project
         # use cloud asset inventory to fetch projects
         source: inventory
         query:
           # org scope is required for using cloud asset inventory on projects & folders
           - scope: organizations/1122333444
           # network folder id / only look at projects under this tree
           - subtree: folders/123333333
         filters:
           - "tag:owner": absent
         actions:
           - type: propagate-labels
             # root-parent allows our sub folder keys in the json to
             # be specified relative to the specifiedroot-parent. in
             # this case we'll do it relative to the network folder by
             # id.
             root-parent: folders/123333333
             folder-labels:
                url: file://folder-labels.json


    note the above policy also uses cloud asset inventory. updates to cloud asset inventory can
    take some time to reflect in this source.
    """
    schema = type_schema(
        'propagate-labels',
        required=('folder-labels',),
        **{
            'root-parent': {'type': 'string'},
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

    def get_root_parent(self):
        root_parent = self.data.get('root-parent')
        if not root_parent:
            return root_parent
        if root_parent.startswith('folders/'):
            root_parent = root_parent.split('/')[-1]
        return root_parent

    def resolve_paths(self):
        self.folder_paths = {}

        root_parent = self.get_root_parent()

        def get_path_segments(fid):
            if root_parent and fid == root_parent:
                return
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
