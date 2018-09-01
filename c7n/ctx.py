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

from c7n.output import FSOutput, MetricsOutput, CloudWatchLogOutput
from c7n.utils import reset_session_cache, dumps
from c7n.version import version

from c7n.resources.aws import ApiStats, SystemStats, XrayTracer


class ExecutionContext(object):
    """Policy Execution Context."""

    def __init__(self, session_factory, policy, options):
        self.policy = policy
        self.options = options
        self.session_factory = session_factory
        self.cloudwatch_logs = None
        self.api_stats = None
        self.start_time = None

        metrics_enabled = getattr(options, 'metrics_enabled', None)
        factory = MetricsOutput.select(metrics_enabled)
        self.metrics = factory(self)

        output_dir = getattr(options, 'output_dir', '')
        if output_dir:
            factory = FSOutput.select(output_dir)
            self.output_path = factory.join(output_dir, policy.name)
            self.output = factory(self)
        else:
            self.output_path = self.output = None

        if options.log_group:
            self.cloudwatch_logs = CloudWatchLogOutput(self)

        self.api_stats = ApiStats(self)
        self.tracer = XrayTracer(self)
        self.sys_stats = SystemStats(self)
        self.execution_id = None

    @property
    def log_dir(self):
        if self.output:
            return self.output.root_dir

    def __enter__(self):
        self.execution_id = str(uuid.uuid4())
        if self.sys_stats:
            self.sys_stats.__enter__()
        if self.output:
            self.output.__enter__()
        if self.cloudwatch_logs:
            self.cloudwatch_logs.__enter__()
        if self.api_stats:
            self.api_stats.__enter__()
        if self.tracer:
            self.tracer.__enter__()
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        self.policy._write_file('metadata.json', dumps(self.get_metadata(), indent=2))
        self.api_stats.__exit__(exc_type, exc_value, exc_traceback)
        if exc_type is not None:
            self.metrics.put_metric('PolicyException', 1, "Count")

        # clear policy execution thread local session cache
        reset_session_cache()

        with self.tracer.subsegment('output'):
            self.metrics.flush()
            if self.cloudwatch_logs:
                self.cloudwatch_logs.__exit__(exc_type, exc_value, exc_traceback)
                self.cloudwatch_logs = None

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
