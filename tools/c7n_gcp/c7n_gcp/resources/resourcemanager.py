# Copyright 2018 Capital One Services, LLC
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.actions import SetIamPolicy, MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo

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
        perm_service = 'resourcemanager'
        permissions = ('resourcemanager.organizations.get',)


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
            "name", "displayName", "lifecycleState", "createTime", "parent"]
        asset_type = "cloudresourcemanager.googleapis.com/Project"
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

    def get_resource_query(self):
        # https://cloud.google.com/resource-manager/reference/rest/v1/projects/list
        if 'query' in self.data:
            for child in self.data.get('query'):
                if 'filter' in child:
                    return {'filter': child['filter']}


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
        folder_ids = set()
        session = local_session(self.manager.session_factory)
        for r in resources:
            client = self.get_client(session, self.manager.resource_type)
            ancestors = client.execute_command(
                'getAncestry', {'projectId': r['projectId']}).get('ancestor')
            parents[r['projectId']] = ancestors
            for a in ancestors[1:-1]:
                if a['resourceId']['type'] != 'folder':
                    continue
                folder_ids.add(a['resourceId']['id'])
        self.parents = parents
        self.folder_ids = folder_ids

    def load_folders(self):
        folder_manager = self.manager.get_resource_manager('gcp.folder')
        self.folders = {
            f['name'].split('/', 1)[-1]: f for f in
            folder_manager.get_resources(list(self.folder_ids))}

    def load_metadata(self, folders):
        raise NotImplementedError()

    def diff(self, resources):
        raise NotImplementedError()

    def process(self, resources):
        self.load_hierarchy(resources)
        self.load_metadata()
        op_set = self.diff(resources)
        client = self.resource_manager.get_client()
        for op in op_set:
            self.invoke_op(client, *op)
