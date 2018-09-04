# Copyright 2015-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

import time
import uuid

from c7n.output import (
    api_stats_outputs,
    blob_outputs,
    log_outputs,
    metrics_outputs,
    sys_stats_outputs,
    tracer_outputs)

from c7n.utils import reset_session_cache, dumps
from c7n.version import version


class ExecutionContext(object):
    """Policy Execution Context."""

    def __init__(self, session_factory, policy, options):
        self.policy = policy
        self.options = options
        self.session_factory = session_factory
        self.start_time = None
        self.execution_id = None

        self.metrics = metrics_outputs.select(options.metrics_enabled, self)
        self.output = blob_outputs.select(options.output_dir, self)
        self.logs = log_outputs.select(options.log_group, self)
        self.tracer = tracer_outputs.select(options.tracer, self)

        # Look for customizations, but fallback to default
        for api_stats_type in (self.policy.provider_name, 'default'):
            if api_stats_type in api_stats_outputs:
                self.api_stats = api_stats_outputs.select(api_stats_type, self)
                break
        for sys_stats_type in ('psutil', 'default'):
            if sys_stats_type in sys_stats_outputs:
                self.sys_stats = sys_stats_outputs.select(sys_stats_type, self)
                break

    @property
    def log_dir(self):
        if self.output:
            return self.output.root_dir

    def __enter__(self):
        self.start_time = time.time()
        self.execution_id = str(uuid.uuid4())
        self.sys_stats.__enter__()
        self.output.__enter__()
        self.logs.__enter__()
        self.api_stats.__enter__()
        self.tracer.__enter__()
        return self

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        if exc_type is not None:
            self.metrics.put_metric('PolicyException', 1, "Count")

        self.policy._write_file('metadata.json', dumps(self.get_metadata(), indent=2))
        self.api_stats.__exit__(exc_type, exc_value, exc_traceback)

        # clear policy execution thread local session cache
        reset_session_cache()

        with self.tracer.subsegment('output'):
            self.metrics.flush()
            self.logs.__exit__(exc_type, exc_value, exc_traceback)
            self.logs = None
            self.output.__exit__(exc_type, exc_value, exc_traceback)

        self.tracer.__exit__()

    def get_metadata(self, include=('sys-stats', 'api-stats', 'metrics')):
        t = time.time()
        md = {
            'policy': self.policy.data,
            'version': version,
            'execution': {
                'id': self.execution_id,
                'start': self.start_time,
                'end_time': t,
                'duration': t - self.start_time},
            'config': dict(self.options)
        }

        if 'sys-stats' in include and self.sys_stats:
            md['sys-stats'] = self.sys_stats.get_metadata()
        if 'api-stats' in include and self.api_stats:
            md['api-stats'] = self.api_stats.get_metadata()
        if 'metrics' in include and self.metrics:
            md['metrics'] = self.metrics.get_metadata()
        return md
