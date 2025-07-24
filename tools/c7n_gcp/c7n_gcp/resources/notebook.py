# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from concurrent.futures import as_completed
from c7n.actions import Action
from c7n.utils import local_session
from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, GcpLocation
from c7n_gcp.client import _create_service_api
from googleapiclient import discovery
import requests
import json


@resources.register('notebook')
class NotebookInstance(QueryResourceManager):
    """ GC resource: https://cloud.google.com/vertex-ai/docs/workbench/reference/rest

    GCP Vertex AI Workbench has public IPs.

    :example: GCP Vertex AI Workbench has public IPs

    .. yaml:

     policies:
      - name: gcp-vertex-ai-workbench-with-public-ips
        description: |
          GCP Vertex AI Workbench has public IPs
        resource: gcp.notebook
        filters:
          - type: value
            key: noPublicIp
            value: true
    """
    class resource_type(TypeInfo):
        service = 'notebooks'
        version = 'v1'
        component = 'projects.locations.instances'
        enum_spec = ('list', 'instances[]', None)
        scope_key = 'parent'
        name = id = 'name'
        scope_template = "projects/{}/locations/-"
        permissions = ('notebooks.instances.list',)
        default_report_fields = ['name', 'createTime', 'state']
        urn_id_segments = (-1,)
        urn_component = "instances"

        @classmethod
        def _get_location(cls, resource):
            return resource['name'].split('/')[3]


@resources.register('notebook-runtime')
class NotebookRuntime(QueryResourceManager):
    """GCP Vertex AI Notebook Runtime resource

    https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.notebookRuntimes

    Vertex AI Notebook Runtimes provide managed Jupyter notebook environments.

    :example: Find all notebook runtimes in a specific state

    .. code-block:: yaml

        policies:
          - name: gcp-vertex-ai-notebook-runtime-running
            description: |
              Find all running Vertex AI notebook runtimes
            resource: gcp.notebook-runtime
            filters:
              - type: value
                key: runtimeState
                value: RUNNING
    """

    class resource_type(TypeInfo):
        service = 'aiplatform'
        version = 'v1'
        component = 'projects.locations.notebookRuntimes'
        enum_spec = ('list', 'notebookRuntimes[]', None)
        scope = None
        scope_key = 'parent'
        name = id = 'name'
        permissions = ('aiplatform.notebookRuntimes.list',)
        default_report_fields = ['name', 'createTime', 'updateTime', 'state', 'healthState']
        urn_component = "notebookRuntime"
        urn_id_segments = (-1,)

        @staticmethod
        def get(client, resource_info):
            name = 'projects/{}/locations/{}/notebookRuntimes/{}' \
                .format(resource_info['project_id'],
                        resource_info['location'],
                        resource_info['notebook_runtime_id'])
            return client.execute_command('get', {'name': name})

        @classmethod
        def _get_location(cls, resource):
            return resource['name'].split('/')[3]

    def get_resource_query(self):
        if 'query' in self.data:
            for child in self.data.get('query'):
                if 'location' in child:
                    location_query = child['location']
                    return {'parent': location_query if isinstance(
                        location_query, list) else [location_query]}
        return None

    def _fetch_resources(self, query):
        """Fetch notebook runtimes from all regions in parallel."""
        session = local_session(self.session_factory)
        project = session.get_default_project()

        # Get locations that support Vertex AI
        locations = (query['parent'] if query and 'parent' in query
                    else GcpLocation.get_service_locations('aiplatform'))

        all_runtimes = []

        # Use Cloud Custodian's executor factory for parallel execution
        # Limit to 3 workers to respect API rate limits
        with self.executor_factory(max_workers=3) as executor:
            # Submit all regional requests concurrently
            future_to_location = {
                executor.submit(self._fetch_region_resources, session, project, location): location
                for location in locations
            }

            # Collect results as they complete
            for future in as_completed(future_to_location):
                location = future_to_location[future]
                try:
                    runtimes = future.result()
                    all_runtimes.extend(runtimes)
                except Exception as e:
                    self.log.warning(f"Failed to fetch runtimes from {location}: {e}")
                    continue

        return self.augment(all_runtimes)

    def _fetch_region_resources(self, session, project, location):
        """Fetch notebook runtimes from a single region."""
        try:
            # Make direct HTTP request to regional endpoint
            parent = f'projects/{project}/locations/{location}'
            url = f'https://{location}-aiplatform.googleapis.com/v1/{parent}/notebookRuntimes'

            # Get access token from session credentials
            credentials = session._credentials

            # Create an HTTP object if session doesn't have one
            if not hasattr(session, '_http') or session._http is None:
                import google.auth.transport.requests
                request = google.auth.transport.requests.Request()
            else:
                request = session._http.request

            credentials.refresh(request)
            access_token = credentials.token

            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()

                # Extract notebook runtimes from response
                if 'notebookRuntimes' in data:
                    return data['notebookRuntimes']
                else:
                    return []
            else:
                self.log.warning(f'HTTP {response.status_code} error fetching from {location}: {response.text}')
                return []

        except Exception as e:
            # Log error and return empty list for this region
            self.log.error(f'Error fetching notebook runtimes from {location}: {e}')
            return []


@NotebookRuntime.action_registry.register('stop')
class StopNotebookRuntime(Action):
    """Stop a Vertex AI Notebook Runtime.

    :example: Stop all running notebook runtimes

    .. code-block:: yaml

        policies:
          - name: stop-running-notebook-runtimes
            resource: gcp.notebook-runtime
            filters:
              - type: value
                key: runtimeState
                value: RUNNING
            actions:
              - type: stop
    """

    schema = {
        'type': 'object',
        'properties': {
            'type': {'enum': ['stop']}
        }
    }

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        project = session.get_default_project()

        for resource in resources:
            try:
                # Extract location from resource name
                # Format: projects/{project}/locations/{location}/notebookRuntimes/{runtime_id}
                location = resource['name'].split('/')[3]
                runtime_name = resource['name']

                # Stop endpoint
                url = f'https://{location}-aiplatform.googleapis.com/v1/{runtime_name}:stop'

                # Get access token
                credentials = session._credentials
                if not hasattr(session, '_http') or session._http is None:
                    import google.auth.transport.requests
                    request = google.auth.transport.requests.Request()
                else:
                    request = session._http.request

                credentials.refresh(request)
                access_token = credentials.token

                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }

                # Make the stop request
                response = requests.post(url, headers=headers, json={})

                if response.status_code in [200, 202]:
                    self.log.info(f'Successfully initiated stop for notebook runtime: {runtime_name}')
                else:
                    self.log.error(f'Failed to stop notebook runtime {runtime_name}: HTTP {response.status_code} - {response.text}')

            except Exception as e:
                self.log.error(f'Error stopping notebook runtime {resource.get("name", "unknown")}: {e}')


@NotebookRuntime.action_registry.register('delete')
class DeleteNotebookRuntime(Action):
    """Delete a Vertex AI Notebook Runtime.

    :example: Delete stopped notebook runtimes

    .. code-block:: yaml

        policies:
          - name: delete-stopped-notebook-runtimes
            resource: gcp.notebook-runtime
            filters:
              - type: value
                key: runtimeState
                value: STOPPED
            actions:
              - type: delete
    """

    schema = {
        'type': 'object',
        'properties': {
            'type': {'enum': ['delete']}
        }
    }

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        project = session.get_default_project()

        for resource in resources:
            try:
                # Extract location from resource name
                # Format: projects/{project}/locations/{location}/notebookRuntimes/{runtime_id}
                location = resource['name'].split('/')[3]
                runtime_name = resource['name']

                # Delete endpoint
                url = f'https://{location}-aiplatform.googleapis.com/v1/{runtime_name}'

                # Get access token
                credentials = session._credentials
                if not hasattr(session, '_http') or session._http is None:
                    import google.auth.transport.requests
                    request = google.auth.transport.requests.Request()
                else:
                    request = session._http.request

                credentials.refresh(request)
                access_token = credentials.token

                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }

                # Make the delete request
                response = requests.delete(url, headers=headers)

                if response.status_code in [200, 202, 204]:
                    self.log.info(f'Successfully initiated deletion for notebook runtime: {runtime_name}')
                else:
                    self.log.error(f'Failed to delete notebook runtime {runtime_name}: HTTP {response.status_code} - {response.text}')

            except Exception as e:
                self.log.error(f'Error deleting notebook runtime {resource.get("name", "unknown")}: {e}')
