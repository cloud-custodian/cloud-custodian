# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import os
from unittest.mock import MagicMock, Mock, patch

from azure.core.pipeline import PipelineContext, PipelineRequest, PipelineResponse
from azure.core.rest import HttpRequest

from c7n import output
from c7n.output import LogMetrics
from c7n_azure.session import ApiStats
from c7n_azure.utils import ApiStatsHookPolicy, api_call_name, custodian_azure_send_override

from .azure_common import BaseTest, cassette_name

ARM = "https://management.azure.com"


class ApiStatsTest(BaseTest):

    @cassette_name('virtual_machine')
    def test_policy_run_records_api_calls(self):
        output_dir = self.get_temp_dir()
        p = self.load_policy(
            {'name': 'azure-vms', 'resource': 'azure.vm'}, output_dir=output_dir)
        metrics = []
        with patch.object(LogMetrics, "_put_metrics", lambda self, ns, m: metrics.extend(m)):
            p.run()

        with open(os.path.join(output_dir, 'azure-vms', 'metadata.json')) as fh:
            metadata = json.load(fh)
        self.assertEqual(metadata['api-stats'], {'GET Microsoft.Compute/virtualMachines': 1})

        by_name = {m['MetricName']: m for m in metrics}
        self.assertEqual(by_name['ApiCalls']['Value'], 1)
        self.assertGreater(p.ctx.api_stats.api_time, 0)
        self.assertEqual(by_name['ApiTime']['Value'], round(p.ctx.api_stats.api_time, 3))
        self.assertEqual(output._api_call_recorders, [])

    def test_api_call_name(self):
        sub = ARM + "/subscriptions/0000/resourceGroups/rg1/providers"
        cases = [
            (ARM + "/subscriptions/0000/providers/Microsoft.Compute/virtualMachines"
             "?api-version=2020-12-01", 'get', 'GET Microsoft.Compute/virtualMachines'),
            (sub + "/Microsoft.Compute/virtualMachines/vm1", 'GET',
             'GET Microsoft.Compute/virtualMachines'),
            (sub + "/Microsoft.Compute/virtualMachines/vm1/powerOff", 'POST',
             'POST Microsoft.Compute/virtualMachines/powerOff'),
            (sub + "/Microsoft.Sql/servers/s1/databases", 'GET',
             'GET Microsoft.Sql/servers/databases'),
            (sub + "/Microsoft.Compute/virtualMachines/vm1/providers/"
             "Microsoft.Insights/diagnosticSettings/ds1", 'PUT',
             'PUT Microsoft.Insights/diagnosticSettings'),
            (ARM + "/subscriptions/0000/resourcegroups", 'GET', 'GET subscriptions/resourcegroups'),
            (ARM + "/providers/Microsoft.Management/managementGroups/mg1/descendants", 'GET',
             'GET Microsoft.Management/managementGroups/descendants'),
            ("https://acct.blob.core.windows.net/container/blob?comp=list", 'GET',
             'GET blob.core.windows.net'),
            ("https://myvault.vault.azure.net/secrets/s1", 'GET', 'GET vault.azure.net'),
            ("https://graph.microsoft.com/v1.0/users/u1", 'GET', 'GET graph.microsoft.com'),
        ]
        for url, method, expected in cases:
            self.assertEqual(api_call_name(method, url), expected, url)

    def pipeline_request(self, method, url):
        return PipelineRequest(HttpRequest(method, url), PipelineContext(None))

    def test_hook_policy_records_attempts_and_runs_hooks(self):
        request_hook, response_hook = Mock(), Mock()
        policy = ApiStatsHookPolicy(raw_request_hook=request_hook, raw_response_hook=response_hook)
        url = ARM + "/subscriptions/0000/providers/Microsoft.Web/sites"
        stats = ApiStats(MagicMock())
        stats.__enter__()
        try:
            request = self.pipeline_request('GET', url)
            policy.on_request(request)
            response = PipelineResponse(request.http_request, Mock(), request.context)
            policy.on_response(request, response)
            # A retried attempt that fails without a response, e.g. a connection error.
            policy.on_request(request)
            policy.on_exception(request)
        finally:
            stats.__exit__()

        self.assertEqual(stats.get_metadata(), {'GET Microsoft.Web/sites': 2})
        self.assertEqual(request_hook.call_count, 2)
        self.assertEqual(response_hook.call_count, 1)

    def test_legacy_send_records_each_attempt(self):
        client = Mock()
        throttled = Mock(status_code=429, headers={'Retry-After': '1'})
        ok = Mock(status_code=200, headers={})
        client.orig_send.side_effect = [throttled, ok]
        request = Mock(method='GET', url="https://graph.windows.net/0000/users?api-version=1.6")
        stats = ApiStats(MagicMock())
        stats.__enter__()
        try:
            with patch('c7n_azure.utils.time.sleep'):
                self.assertIs(custodian_azure_send_override(client, request), ok)
        finally:
            stats.__exit__()
        self.assertEqual(stats.get_metadata(), {'GET graph.windows.net': 2})
