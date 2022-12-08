# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
import uuid
import os


from c7n.output import (
    api_stats_outputs,
    blob_outputs,
    log_outputs,
    metrics_outputs,
    sys_stats_outputs,
    tracer_outputs,
)

from c7n.utils import reset_session_cache, dumps, local_session
from c7n.version import version


class ExecutionContext:
    """Policy Execution Context."""

    def __init__(self, session_factory, policy, options):
        self.policy = policy
        self.options = options
        self.session_factory = session_factory

        # Runtime initialized during policy execution
        # We treat policies as a fly weight pre-execution.
        self.start_time = None
        self.execution_id = None
        self.output = None
        self.logs = None
        self.api_stats = None
        self.sys_stats = None

        # A few tests patch on metrics flush
        # For backward compatibility, accept both 'metrics' and 'metrics_enabled' params (PR #4361)
        metrics = self.options.metrics or self.options.metrics_enabled
        self.metrics = metrics_outputs.select(metrics, self)

        # Tracer is wired into core filtering code / which is getting
        # invoked sans execution context entry in tests
        self.tracer = tracer_outputs.select(self.options.tracer, self)

    def initialize(self):
        self.output = blob_outputs.select(self.options.output_dir, self)
        self.logs = log_outputs.select(self.options.log_group, self)

        # Always do file/blob storage outputs
        self.output_logs = None
        if not isinstance(self.logs, (log_outputs['default'], log_outputs['null'])):
            self.output_logs = log_outputs.select(None, self)

        # Look for customizations, but fallback to default
        for api_stats_type in (self.policy.provider_name, 'default'):
            if api_stats_type in api_stats_outputs:
                self.api_stats = api_stats_outputs.select(api_stats_type, self)
                break
        for sys_stats_type in ('psutil', 'default'):
            if sys_stats_type in sys_stats_outputs:
                self.sys_stats = sys_stats_outputs.select(sys_stats_type, self)
                break

        self.start_time = time.time()
        self.execution_id = str(uuid.uuid4())

    @property
    def log_dir(self):
        return self.output.root_dir

    def __enter__(self):
        self.initialize()
        self.session_factory.policy_name = self.policy.name
        self.sys_stats.__enter__()
        self.output.__enter__()
        self.logs.__enter__()
        if self.output_logs:
            self.output_logs.__enter__()

        self.api_stats.__enter__()
        self.tracer.__enter__()

        # Api stats and user agent modification by policy require updating
        # in place the cached session thread local.
        update_session = getattr(self.session_factory, 'update', None)
        if update_session:
            update_session(local_session(self.session_factory))
        return self

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        if exc_type is not None and self.metrics:
            self.metrics.put_metric('PolicyException', 1, "Count")
        self.output.write_file('metadata.json', dumps(self.get_metadata(), indent=2))
        self.api_stats.__exit__(exc_type, exc_value, exc_traceback)

        with self.tracer.subsegment('output'):
            self.metrics.flush()
            self.logs.__exit__(exc_type, exc_value, exc_traceback)
            if self.output_logs:
                self.output_logs.__exit__(exc_type, exc_value, exc_traceback)
            self.output.__exit__(exc_type, exc_value, exc_traceback)

        self.tracer.__exit__()

        self.session_factory.policy_name = None
        # IMPORTANT: multi-account execution (c7n-org and others) need
        # to manually reset this.  Why: Not doing this means we get
        # excessive memory usage from client reconstruction for dynamic-gen
        # sdks.
        if os.environ.get('C7N_TEST_RUN'):
            reset_session_cache()

    def get_metadata(self, include=('sys-stats', 'api-stats', 'metrics')):
        t = time.time()
        md = {
            'policy': self.policy.data,
            'version': version,
            'execution': {
                'id': self.execution_id,
                'start': self.start_time,
                'end_time': t,
                'duration': t - self.start_time,
            },
            'config': dict(self.options),
        }

        if 'sys-stats' in include and self.sys_stats:
            md['sys-stats'] = self.sys_stats.get_metadata()
        if 'api-stats' in include and self.api_stats:
            md['api-stats'] = self.api_stats.get_metadata()
        if 'metrics' in include and self.metrics:
            md['metrics'] = self.metrics.get_metadata()
        return md
