# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import re
from urllib.parse import urlsplit, urlunsplit

import isodate
import requests

from azure.core.exceptions import HttpResponseError
from azure.mgmt.machinelearningservices.models import (
    ClusterUpdateParameters,
    ScaleSettings,
    ScaleSettingsInformation,
)

from c7n.exceptions import PolicyValidationError
from c7n.filters.core import Filter, type_schema
from c7n_azure import utils
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.utils import ResourceIdParser


WORKSPACE_DISCOVERY_URL = 'c7n:WorkspaceDiscoveryUrl'
DURATION_UNITS = {
    'm': 'minutes',
    'h': 'hours',
    'd': 'days',
    'w': 'weeks',
}
# The Run History audience is not one of the cloud's ARM endpoints.
AML_AUDIENCES = {
    'AzureCloud': 'https://ml.azure.com',
    'AzureChinaCloud': 'https://ml.azure.cn',
    'AzureUSGovernment': 'https://ml.azure.us',
}
# Every Run History run status except terminal Completed/Failed/Canceled.
NONTERMINAL_STATUSES = (
    'NotStarted',
    'Starting',
    'Provisioning',
    'Preparing',
    'Queued',
    'Running',
    'Finalizing',
    'CancelRequested',
    'NotResponding',
    'Unapproved',
    'Pausing',
    'Paused',
)


@resources.register('machine-learning-compute-cluster')
class MachineLearningComputeCluster(ChildArmResourceManager):
    """Azure Machine Learning AmlCompute cluster resource.

    :example:

    Find allocated AmlCompute clusters.

    .. code-block:: yaml

        policies:
          - name: machine-learning-compute-clusters-allocated
            resource: azure.machine-learning-compute-cluster
            filters:
              - type: value
                key: properties.properties.currentNodeCount
                op: gt
                value: 0
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        service = 'azure.mgmt.machinelearningservices'
        client = 'MachineLearningServicesMgmtClient'
        enum_spec = ('compute', 'list', None)
        parent_manager_name = 'machine-learning-workspace'
        resource_type = 'Microsoft.MachineLearningServices/workspaces/computes'
        default_report_fields = (
            'name',
            'resourceGroup',
            '"c7n:parent-id"',
            'properties.properties.currentNodeCount',
            'properties.properties.nodeStateCounts.runningNodeCount',
            'properties.properties.scaleSettings.minNodeCount',
            'properties.properties.scaleSettings.maxNodeCount',
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': parent_resource['resourceGroup'],
                'workspace_name': parent_resource['name'],
            }

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
        resources = super().enumerate_resources(
            parent_resource,
            type_info,
            vault_url=vault_url,
            **params,
        )
        clusters = [
            resource for resource in resources
            if resource['properties']['computeType'] == 'AmlCompute'
        ]
        discovery_url = parent_resource['properties'].get('discoveryUrl')
        for cluster in clusters:
            cluster[WORKSPACE_DISCOVERY_URL] = discovery_url
        return clusters


@MachineLearningComputeCluster.filter_registry.register('inactive')
class InactiveFilter(Filter):
    """Find clusters with no current or recent job activity.

    :example:

    .. code-block:: yaml

        policies:
          - name: machine-learning-compute-clusters-inactive
            resource: azure.machine-learning-compute-cluster
            filters:
              - type: value
                key: properties.properties.currentNodeCount
                op: gt
                value: 0
              - type: inactive
                since: 1d
    """

    schema = type_schema(
        'inactive',
        required=['since'],
        since={
            'type': 'string',
            'pattern': r'^[1-9][0-9]*[mhdw]$',
        },
    )

    def validate(self):
        # Policy-level schema validation does not enforce this filter's
        # `required`, so a missing `since` only fails here.
        if 'since' not in self.data:
            raise PolicyValidationError("inactive filter requires 'since'")
        return self

    def process(
        self,
        resources: list[dict],
        event=None,
    ) -> list[dict]:
        match = re.fullmatch(r'([1-9][0-9]*)([mhdw])', self.data['since'])
        amount, unit = match.groups()
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            **{DURATION_UNITS[unit]: int(amount)}
        )

        workspaces = {}
        for resource in resources:
            node_counts = resource['properties'].get('properties', {}).get(
                'nodeStateCounts',
                {},
            )
            if node_counts.get('runningNodeCount', 0) > 0:
                continue
            workspaces.setdefault(resource['c7n:parent-id'], []).append(resource)

        inactive = []
        for workspace_resources in workspaces.values():
            workspace = workspace_resources[0]
            if not workspace.get(WORKSPACE_DISCOVERY_URL):
                self.log.warning(
                    'Workspace %s has no discovery URL; skipping inactivity check',
                    workspace['c7n:parent-id'],
                )
                continue
            try:
                targets = self._get_active_targets(workspace, cutoff)
            except requests.RequestException as error:
                self.log.warning(
                    'Run History query failed for workspace %s: %s',
                    workspace['c7n:parent-id'],
                    error,
                )
                continue
            inactive.extend(
                resource for resource in workspace_resources
                if resource['name'].lower() not in targets
            )
        return inactive

    def _query_history(self, url: str, body: dict) -> list[dict]:
        azure_session = self.manager.get_session()
        audience = AML_AUDIENCES[azure_session.cloud_endpoints.name]
        session = utils.requests_session(
            azure_session,
            token_scope=f'{audience}/.default',
            max_retries=3,
            allowed_methods=('POST',),
        )
        headers = {'Content-Type': 'application/json'}
        params = {'api-version': '2023-10-01'}
        values = []
        request_body = dict(body)

        while True:
            response = session.post(
                url,
                headers=headers,
                params=params,
                json=request_body,
                timeout=30,
            )
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, dict) or not isinstance(page.get('value'), list):
                raise TypeError('Run History response value must be a list')
            values.extend(page['value'])
            continuation_token = page.get('continuationToken')
            if not continuation_token:
                return values
            request_body = dict(body)
            request_body['continuationToken'] = continuation_token

    def _get_experiments(self, workspace: dict) -> list[str]:
        endpoint = self._get_history_endpoint(workspace)
        workspace_id = workspace['c7n:parent-id']
        url = f'{endpoint}/history/v1.0{workspace_id}/experiments:query'
        # Archiving an experiment does not end its runs, so a non-terminal run
        # can live in an experiment archived long before the cutoff.
        experiments = self._query_history(url, {'viewType': 'All'})

        experiment_ids = []
        seen = set()
        for experiment in experiments:
            experiment_id = experiment.get('experimentId')
            if experiment_id and experiment_id not in seen:
                experiment_ids.append(experiment_id)
                seen.add(experiment_id)
        return experiment_ids

    def _get_active_targets(
        self,
        workspace: dict,
        cutoff: datetime.datetime,
    ) -> set[str]:
        endpoint = self._get_history_endpoint(workspace)
        workspace_id = workspace['c7n:parent-id']
        cutoff_text = self._format_cutoff(cutoff)
        status_filter = ' or '.join(
            f"status eq '{status}'" for status in NONTERMINAL_STATUSES
        )
        targets = set()

        for experiment_id in self._get_experiments(workspace):
            url = (
                f'{endpoint}/history/v1.0{workspace_id}/experimentids/'
                f'{experiment_id}/runs:query'
            )
            runs = self._query_history(url, {'filter': status_filter})
            runs.extend(self._query_history(
                url,
                {'filter': f'endTimeUtc ge {cutoff_text}'},
            ))
            for run in runs:
                target = run.get('target')
                if isinstance(target, str) and target:
                    targets.add(target.lower())
        return targets

    @staticmethod
    def _get_history_endpoint(workspace: dict) -> str:
        discovery_url = workspace[WORKSPACE_DISCOVERY_URL]
        parts = urlsplit(discovery_url)
        if not parts.path.endswith('/discovery'):
            raise ValueError('Workspace discovery URL must end in /discovery')
        path = parts.path[:-len('/discovery')]
        return urlunsplit((parts.scheme, parts.netloc, path, '', ''))

    @staticmethod
    def _format_cutoff(cutoff: datetime.datetime) -> str:
        return cutoff.astimezone(datetime.timezone.utc).isoformat().replace(
            '+00:00',
            'Z',
        )


@MachineLearningComputeCluster.action_registry.register('set-min-nodes')
class SetMinNodesAction(AzureBaseAction):
    """Set a cluster's minimum node count.

    This preserves the cluster and its maximum and idle scale-down settings.

    :example:

    Set the minimum node count to zero.

    .. code-block:: yaml

        policies:
          - name: machine-learning-compute-clusters-set-min-nodes
            resource: azure.machine-learning-compute-cluster
            actions:
              - type: set-min-nodes
                value: 0
    """

    schema = type_schema(
        'set-min-nodes',
        required=['value'],
        value={
            'type': 'integer',
            'minimum': 0,
        },
    )

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        scale_settings = resource['properties']['properties']['scaleSettings']
        idle_time = scale_settings.get('nodeIdleTimeBeforeScaleDown')
        parameters = ClusterUpdateParameters(
            properties=ScaleSettingsInformation(
                scale_settings=ScaleSettings(
                    max_node_count=scale_settings['maxNodeCount'],
                    min_node_count=self.data['value'],
                    node_idle_time_before_scale_down=(
                        isodate.parse_duration(idle_time)
                        if idle_time else None
                    ),
                ),
            ),
        )
        try:
            self.client.compute.begin_update(
                resource_group_name=ResourceIdParser.get_resource_group(
                    resource['id']
                ),
                workspace_name=ResourceIdParser.get_resource_name(
                    resource['c7n:parent-id']
                ),
                compute_name=resource['name'],
                parameters=parameters,
            )
        except HttpResponseError as error:
            # The service can accept updates with 202, which this SDK rejects.
            if error.response is None or error.response.status_code != 202:
                raise
