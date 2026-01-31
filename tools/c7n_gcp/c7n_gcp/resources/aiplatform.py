# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.actions import MethodAction
from c7n.filters import Filter
from c7n.utils import type_schema, local_session
from googleapiclient.discovery import build
from google.api_core.client_options import ClientOptions
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

log = logging.getLogger('custodian.gcp.aiplatform')


@resources.register('vertex-endpoint')
class VertexEndpoint(QueryResourceManager):
    """GCP Vertex AI Endpoint Resource

    https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.endpoints
    """

    class resource_type(TypeInfo):
        service = 'aiplatform'
        version = 'v1'
        component = 'projects.locations.endpoints'
        enum_spec = ('list', 'endpoints[]', None)
        scope_key = 'parent'
        name = 'displayName'
        id = 'name'
        scope_template = "projects/{}/locations/-"
        permissions = (
            'aiplatform.endpoints.list',
            'aiplatform.locations.list',
        )
        default_report_fields = [
            'name',
            'displayName',
            'createTime',
            'deployedModels',
        ]

        @classmethod
        def _get_location(cls, resource):
            # Format: projects/{project}/locations/{location}/endpoints/{id}
            return resource['name'].split('/')[3]

    def resources(self, query=None):
        if query:
            return super().resources(query)

        results = []
        session = local_session(self.session_factory)
        project_id = session.get_default_project()

        try:
            creds = session.get_credentials()
        except AttributeError:
            creds = getattr(session, '_credentials', None)

        if not creds:
            import google.auth

            creds, _ = google.auth.default()

        # 1. Get List of Regions
        locations = []
        try:
            global_service = build(
                'aiplatform', 'v1', credentials=creds, cache_discovery=False
            )
            request = (
                global_service.projects()
                .locations()
                .list(name=f'projects/{project_id}')
            )
            while request:
                response = request.execute()
                locations.extend(
                    [
                        loc['locationId']
                        for loc in response.get('locations', [])
                    ]
                )
                request = (
                    global_service.projects()
                    .locations()
                    .list_next(
                        previous_request=request, previous_response=response
                    )
                )
        except Exception as e:
            log.warning(f"Could not list locations for Vertex AI: {e}")
            return []

        # 2. Helper for Parallel Execution
        def list_region_endpoints(loc):
            if loc == 'global':
                return []
            region_results = []
            try:
                api_endpoint = f"https://{loc}-aiplatform.googleapis.com"
                client_options = ClientOptions(api_endpoint=api_endpoint)

                # We build a lightweight client per thread
                regional_service = build(
                    'aiplatform',
                    'v1',
                    credentials=creds,
                    cache_discovery=False,
                    client_options=client_options,
                )

                parent = f"projects/{project_id}/locations/{loc}"
                request = (
                    regional_service.projects()
                    .locations()
                    .endpoints()
                    .list(parent=parent)
                )

                while request:
                    response = request.execute()
                    items = response.get('endpoints', [])
                    region_results.extend(items)
                    request = (
                        regional_service.projects()
                        .locations()
                        .endpoints()
                        .list_next(
                            previous_request=request,
                            previous_response=response,
                        )
                    )
            except Exception:
                pass
            return region_results

        # 3. Parallel Scan
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_loc = {
                executor.submit(list_region_endpoints, loc): loc
                for loc in locations
            }
            for future in as_completed(future_to_loc):
                try:
                    data = future.result()
                    results.extend(data)
                except Exception:
                    pass

        return self.filter_resources(results)


@VertexEndpoint.filter_registry.register('empty-endpoint')
class EmptyEndpointFilter(Filter):
    """Filter to identify endpoints with no deployed models."""

    schema = type_schema('empty-endpoint', value={'type': 'boolean'})

    def process(self, resources, event=None):
        results = []
        target_empty = self.data.get('value', True)

        for r in resources:
            models = r.get('deployedModels', [])
            is_empty = len(models) == 0

            if target_empty and is_empty:
                results.append(r)
            elif not target_empty and not is_empty:
                results.append(r)

        return results


@VertexEndpoint.action_registry.register('delete')
class DeleteEndpoint(MethodAction):
    """Deletes a Vertex AI Endpoint.

    This action handles the regional API requirement automatically.
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ('aiplatform.endpoints.delete',)

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        try:
            creds = session.get_credentials()
        except AttributeError:
            creds = getattr(session, '_credentials', None)

        # Group resources by region to reuse clients
        resources_by_region = {}
        for r in resources:
            location = r['name'].split('/')[3]
            if location not in resources_by_region:
                resources_by_region[location] = []
            resources_by_region[location].append(r)

        for location, items in resources_by_region.items():
            try:
                api_endpoint = f"https://{location}-aiplatform.googleapis.com"
                client_options = ClientOptions(api_endpoint=api_endpoint)
                client = build(
                    'aiplatform',
                    'v1',
                    credentials=creds,
                    cache_discovery=False,
                    client_options=client_options,
                )

                for item in items:
                    self.process_resource(client, item)
            except Exception as e:
                log.error(f"Error processing region {location}: {e}")

    def process_resource(self, client, resource):
        try:
            client.projects().locations().endpoints().delete(
                name=resource['name']
            ).execute()
        except Exception as e:
            log.warning(
                f"Failed to delete endpoint {resource['displayName']}: {e}"
            )
