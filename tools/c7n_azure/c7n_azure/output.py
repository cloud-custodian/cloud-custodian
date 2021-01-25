# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Provides output support for Azure Blob Storage using
the 'azure://' prefix

"""
import logging
import os
import shutil
import tempfile

from c7n_azure.storage_utils import StorageUtilities
from c7n_azure.utils import AppInsightsHelper
from c7n.output import (
    blob_outputs,
    log_outputs,
    metrics_outputs,
    DirectoryOutput,
    LogOutput,
    Metrics
)
from c7n.utils import local_session

from applicationinsights import TelemetryClient
from applicationinsights.logging import LoggingHandler
from azure.common import AzureHttpError


@blob_outputs.register('azure')
class AzureStorageOutput(DirectoryOutput):
    """
    Usage:

    .. code-block:: python

       with AzureStorageOutput(session_factory, 'azure://bucket/prefix'):
           log.info('xyz')  # -> log messages sent to custodian-run.log.gz

    """

    DEFAULT_BLOB_FOLDER_PREFIX = '{policy_name}/{now:%Y/%m/%d/%H/}'

    log = logging.getLogger('custodian.azure.output.AzureStorageOutput')

    def __init__(self, ctx, config=None):
        self.ctx = ctx
        self.config = config

        self.root_dir = tempfile.mkdtemp()
        self.output_dir = self.get_output_path(self.ctx.options.output_dir)
        self.blob_service, self.container, self.file_prefix = \
            self.get_blob_client_wrapper(self.output_dir, ctx)

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        if exc_type is not None:
            self.log.exception("Error while executing policy")
        self.log.debug("Uploading policy logs")
        self.compress()
        self.upload()
        shutil.rmtree(self.root_dir)
        self.log.debug("Policy Logs uploaded")

    def get_output_path(self, output_url):
        # if pyformat is not specified, then use the policy name and formatted date
        if '{' not in output_url:
            output_url = self.join(output_url, self.DEFAULT_BLOB_FOLDER_PREFIX)

        return output_url.format(**self.get_output_vars())

    def upload(self):
        for root, dirs, files in os.walk(self.root_dir):
            for f in files:
                blob_name = self.join(self.file_prefix, root[len(self.root_dir):], f)
                blob_name.strip('/')
                try:
                    self.blob_service.create_blob_from_path(
                        self.container,
                        blob_name,
                        os.path.join(root, f))
                except AzureHttpError as e:
                    if e.status_code == 403:
                        self.log.error("Access Error: Storage Blob Data Contributor Role "
                                       "is required to write to Azure Blob Storage.")
                    else:
                        self.log.exception("Error writing output. "
                                           "Confirm output storage URL is correct.")

                self.log.debug("%s uploaded" % blob_name)

    @staticmethod
    def join(*parts):
        return "/".join([s.strip('/') for s in parts if s != ''])

    @staticmethod
    def get_blob_client_wrapper(output_path, ctx):
        # provides easier test isolation
        s = local_session(ctx.session_factory)
        return StorageUtilities.get_blob_client_by_uri(output_path, s)


@metrics_outputs.register('azure')
class MetricsOutput(Metrics):
    """Send metrics data to app insights
    """

    def __init__(self, ctx, config=None):
        super(MetricsOutput, self).__init__(ctx, config)
        self.namespace = self.ctx.policy.name
        self.tc = None

    def _initialize(self):
        if self.tc is not None:
            return
        self.instrumentation_key = AppInsightsHelper.get_instrumentation_key(self.config['url'])
        self.tc = TelemetryClient(self.instrumentation_key)
        self.subscription_id = local_session(self.ctx.policy.session_factory).get_subscription_id()

    def _format_metric(self, key, value, unit, dimensions):
        self._initialize()
        d = {
            'Name': key,
            'Value': value,
            'Dimensions': {
                'Policy': self.ctx.policy.name,
                'ResType': self.ctx.policy.resource_type,
                'SubscriptionId': self.subscription_id,
                'ExecutionId': self.ctx.execution_id,
                'ExecutionMode': self.ctx.policy.execution_mode,
                'Unit': unit
            }
        }
        for k, v in dimensions.items():
            d['Dimensions'][k] = v
        return d

    def _put_metrics(self, ns, metrics):
        self._initialize()
        for m in metrics:
            self.tc.track_metric(name=m['Name'],
                                 value=m['Value'],
                                 properties=m['Dimensions'])
        self.tc.flush()


class AppInsightsLogHandler(LoggingHandler):
    def __init__(self, instrumentation_key, policy_name, subscription_id, execution_id, res_type):
        super(AppInsightsLogHandler, self).__init__(instrumentation_key)
        self.policy_name = policy_name
        self.subscription_id = subscription_id
        self.execution_id = execution_id
        self.resource_type = res_type

    def emit(self, record):
        properties = {
            'Process': record.processName,
            'Module': record.module,
            'FileName': record.filename,
            'LineNumber': record.lineno,
            'Level': record.levelname,
            'Policy': self.policy_name,
            'SubscriptionId': self.subscription_id,
            'ResType': self.resource_type,
            'ExecutionId': self.execution_id
        }

        if hasattr(record, 'properties'):
            properties.update(record.properties)

        if record.exc_info:
            self.client.track_exception(*record.exc_info, properties=properties)
            return

        self.client.track_trace(record.msg, properties=properties, severity=record.levelname)


@log_outputs.register('azure')
class AppInsightsLogOutput(LogOutput):

    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'

    def get_handler(self):
        self.instrumentation_key = AppInsightsHelper.get_instrumentation_key(self.config['url'])
        self.subscription_id = local_session(self.ctx.policy.session_factory).get_subscription_id()
        return AppInsightsLogHandler(self.instrumentation_key,
                                     self.ctx.policy.name,
                                     self.subscription_id,
                                     self.ctx.execution_id,
                                     self.ctx.policy.resource_type)
