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


@resources.register('vertex-ai-endpoint')
class VertexAIEndpoint(QueryResourceManager):
    """GCP Vertex AI Endpoint resource

    https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.endpoints

    Vertex AI Endpoints provide online prediction services for deployed models.

    :example: Find all endpoints with deployed models

    .. code-block:: yaml

        policies:
          - name: gcp-vertex-ai-endpoints-with-models
            description: |
              Find all Vertex AI endpoints that have deployed models
            resource: gcp.vertex-ai-endpoint
            filters:
              - type: value
                key: deployedModels
                value: not-null
    """

    class resource_type(TypeInfo):
        service = 'aiplatform'
        version = 'v1'
        component = 'projects.locations.endpoints'
        enum_spec = ('list', 'endpoints[]', None)
        scope_key = 'parent'
        name = id = 'name'
        scope_template = "projects/{}/locations/{}"
        permissions = ('aiplatform.endpoints.list',)
        default_report_fields = ['name', 'displayName', 'createTime', 'updateTime']
        urn_id_segments = (-1,)
        urn_component = "endpoints"

        @classmethod
        def _get_location(cls, resource):
            return resource['name'].split('/')[3]

    def _fetch_resources(self, query):
        """Fetch Vertex AI endpoints from all available regions in parallel."""
        session = local_session(self.session_factory)
        project = session.get_default_project()
        
        # Get all locations that support aiplatform service
        locations = GcpLocation.get_service_locations('aiplatform')
        if not locations:
            self.log.warning('No aiplatform service locations found')
            return []
        
        self.log.info(f'Fetching Vertex AI endpoints from {len(locations)} regions: {locations}')
        
        # Use Cloud Custodian's executor factory for parallel execution
        with self.executor_factory(max_workers=3) as executor:
            # Submit tasks for each location
            future_to_location = {
                executor.submit(self._fetch_region_endpoints, session, project, location): location
                for location in locations
            }
            
            # Collect results as they complete
            all_endpoints = []
            for future in as_completed(future_to_location):
                location = future_to_location[future]
                try:
                    endpoints = future.result()
                    if endpoints:
                        self.log.info(f'Found {len(endpoints)} endpoints in {location}')
                        all_endpoints.extend(endpoints)
                except Exception as e:
                    self.log.error(f'Error fetching endpoints from {location}: {e}')
        
        self.log.info(f'Total endpoints found: {len(all_endpoints)}')
        
        # Augment resources with additional metadata
        return self.augment(all_endpoints)
    
    def _fetch_region_endpoints(self, session, project, location):
        """Fetch endpoints from a specific region using direct HTTP requests."""
        try:
            # Construct the regional endpoint URL
            url = f'https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/endpoints'
            
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
            
            # Make the API request
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                endpoints = data.get('endpoints', [])
                self.log.debug(f'Successfully fetched {len(endpoints)} endpoints from {location}')
                return endpoints
            else:
                self.log.warning(f'HTTP {response.status_code} error fetching from {location}: {response.text}')
                return []

        except Exception as e:
            # Log error and return empty list for this region
            self.log.error(f'Error fetching endpoints from {location}: {e}')
            return []


@VertexAIEndpoint.action_registry.register('undeploy-model')
class UndeployModelFromEndpoint(Action):
    """Undeploy all models from a Vertex AI Endpoint.

    :example: Undeploy models from all endpoints

    .. code-block:: yaml

        policies:
          - name: undeploy-models-from-endpoints
            resource: gcp.vertex-ai-endpoint
            filters:
              - type: value
                key: deployedModels
                value: not-null
            actions:
              - type: undeploy-model
    """

    schema = {
        'type': 'object',
        'properties': {
            'type': {'enum': ['undeploy-model']}
        }
    }

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        project = session.get_default_project()

        for resource in resources:
            try:
                # Extract location from resource name
                # Format: projects/{project}/locations/{location}/endpoints/{endpoint_id}
                location = resource['name'].split('/')[3]
                endpoint_name = resource['name']
                
                # Check if there are deployed models
                deployed_models = resource.get('deployedModels', [])
                if not deployed_models:
                    self.log.info(f'No deployed models found on endpoint: {endpoint_name}')
                    continue
                
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
                
                # Undeploy each model
                for deployed_model in deployed_models:
                    model_id = deployed_model.get('id')
                    if not model_id:
                        self.log.warning(f'No model ID found for deployed model on endpoint: {endpoint_name}')
                        continue
                    
                    # Undeploy endpoint
                    url = f'https://{location}-aiplatform.googleapis.com/v1/{endpoint_name}:undeployModel'
                    payload = {
                        'deployedModelId': model_id
                    }
                    
                    response = requests.post(url, headers=headers, json=payload)

                    if response.status_code in [200, 202]:
                        self.log.info(f'Successfully initiated undeploy for model {model_id} from endpoint: {endpoint_name}')
                    else:
                        self.log.error(f'Failed to undeploy model {model_id} from endpoint {endpoint_name}: HTTP {response.status_code} - {response.text}')

            except Exception as e:
                self.log.error(f'Error undeploying models from endpoint {resource.get("name", "unknown")}: {e}')


@VertexAIEndpoint.action_registry.register('delete')
class DeleteVertexAIEndpoint(Action):
    """Delete a Vertex AI Endpoint.
    
    Automatically undeploys any deployed models first, waits for completion,
    then deletes the endpoint.

    :example: Delete endpoints (will undeploy models first if needed)

    .. code-block:: yaml

        policies:
          - name: delete-endpoints
            resource: gcp.vertex-ai-endpoint
            actions:
              - type: delete
    """

    schema = {
        'type': 'object',
        'properties': {
            'type': {'enum': ['delete']},
            'wait-timeout': {
                'type': 'integer',
                'default': 600,
                'description': 'Maximum time in seconds to wait for model undeployment'
            }
        }
    }

    def process(self, resources):
        import time
        session = local_session(self.manager.session_factory)
        project = session.get_default_project()
        wait_timeout = self.data.get('wait-timeout', 600)  # Default 10 minutes

        for resource in resources:
            try:
                # Extract location from resource name
                # Format: projects/{project}/locations/{location}/endpoints/{endpoint_id}
                location = resource['name'].split('/')[3]
                endpoint_name = resource['name']
                
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
                
                # Step 1: Check if there are deployed models and undeploy them
                deployed_models = resource.get('deployedModels', [])
                if deployed_models:
                    self.log.info(f'Found {len(deployed_models)} deployed models on endpoint {endpoint_name}. Undeploying first...')
                    
                    # Undeploy each model
                    undeploy_operations = []
                    for deployed_model in deployed_models:
                        model_id = deployed_model.get('id')
                        if not model_id:
                            self.log.warning(f'No model ID found for deployed model on endpoint: {endpoint_name}')
                            continue
                        
                        # Undeploy model
                        undeploy_url = f'https://{location}-aiplatform.googleapis.com/v1/{endpoint_name}:undeployModel'
                        payload = {
                            'deployedModelId': model_id
                        }
                        
                        response = requests.post(undeploy_url, headers=headers, json=payload)
                        
                        if response.status_code in [200, 202]:
                            operation_data = response.json()
                            operation_name = operation_data.get('name')
                            if operation_name:
                                undeploy_operations.append(operation_name)
                                self.log.info(f'Successfully initiated undeploy for model {model_id} from endpoint: {endpoint_name} (operation: {operation_name})')
                            else:
                                self.log.info(f'Successfully initiated undeploy for model {model_id} from endpoint: {endpoint_name} (no operation returned)')
                        else:
                            self.log.error(f'Failed to undeploy model {model_id} from endpoint {endpoint_name}: HTTP {response.status_code} - {response.text}')
                            continue
                    
                    # Step 2: Wait for undeploy operations to complete
                    if undeploy_operations:
                        self.log.info(f'Waiting for {len(undeploy_operations)} undeploy operations to complete...')
                        self._wait_for_operations(undeploy_operations, location, headers, wait_timeout)
                
                # Step 3: Delete the endpoint
                self.log.info(f'Deleting endpoint: {endpoint_name}')
                delete_url = f'https://{location}-aiplatform.googleapis.com/v1/{endpoint_name}'
                response = requests.delete(delete_url, headers=headers)

                if response.status_code in [200, 202, 204]:
                    self.log.info(f'Successfully initiated deletion for endpoint: {endpoint_name}')
                else:
                    self.log.error(f'Failed to delete endpoint {endpoint_name}: HTTP {response.status_code} - {response.text}')

            except Exception as e:
                self.log.error(f'Error deleting endpoint {resource.get("name", "unknown")}: {e}')
    
    def _wait_for_operations(self, operation_names, location, headers, timeout):
        """Wait for long-running operations to complete."""
        import time
        start_time = time.time()
        
        pending_operations = set(operation_names)
        
        while pending_operations and (time.time() - start_time) < timeout:
            completed_operations = set()
            
            for operation_name in list(pending_operations):
                try:
                    # Check operation status
                    operation_url = f'https://{location}-aiplatform.googleapis.com/v1/{operation_name}'
                    response = requests.get(operation_url, headers=headers)
                    
                    if response.status_code == 200:
                        operation_data = response.json()
                        if operation_data.get('done', False):
                            if 'error' in operation_data:
                                error = operation_data['error']
                                self.log.error(f'Operation {operation_name} failed: {error}')
                            else:
                                self.log.info(f'Operation {operation_name} completed successfully')
                            completed_operations.add(operation_name)
                        else:
                            self.log.debug(f'Operation {operation_name} still in progress...')
                    else:
                        self.log.warning(f'Failed to check operation {operation_name}: HTTP {response.status_code}')
                        # Remove from pending to avoid infinite loop
                        completed_operations.add(operation_name)
                        
                except Exception as e:
                    self.log.error(f'Error checking operation {operation_name}: {e}')
                    completed_operations.add(operation_name)
            
            # Remove completed operations
            pending_operations -= completed_operations
            
            if pending_operations:
                self.log.info(f'Waiting for {len(pending_operations)} operations to complete...')
                time.sleep(10)  # Wait 10 seconds before checking again
        
        if pending_operations:
            self.log.warning(f'Timeout reached. {len(pending_operations)} operations may still be pending: {list(pending_operations)}')
        else:
            self.log.info('All undeploy operations completed successfully')
