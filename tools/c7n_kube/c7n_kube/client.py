# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
# Copyright 2017 The Forseti Security Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os
import time
from collections import Counter

from kubernetes import config, client
from kubernetes.client import Configuration, ApiClient

from c7n.output import DeltaStats, api_stats_outputs

log = logging.getLogger("custodian.k8s.client")

# Recorders notified of every api call made through a Session client, set
# by APIStats for the duration of a policy execution. Module level rather
# than per session, as the session factory may be the Session class or a
# partial of it, and cached sessions are recreated on expiry.
_subscribers = []


class InstrumentedAPI:
    """Wraps a kubernetes api object (e.g. CoreV1Api) to report each public
    method call, by method name, with its duration to the subscribers."""

    def __init__(self, api):
        self._api = api

    def __getattr__(self, name):
        attr = getattr(self._api, name)
        if name.startswith("_") or not callable(attr):
            return attr

        def call(*args, **kwargs):
            start = time.perf_counter()
            try:
                return attr(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                for s in _subscribers:
                    s.record(name, elapsed)

        return call


class Session:
    def __init__(self, config_file=None):
        self.config_file = config_file
        self.http_proxy = os.getenv("HTTPS_PROXY")

    def client(self, group, version):
        client_config = Configuration()
        config.load_kube_config(self.config_file, client_configuration=client_config)
        client_config.proxy = self.http_proxy
        api_client = ApiClient(configuration=client_config)
        log.debug("connecting to %s" % (api_client.configuration.host))
        # e.g. client.CoreV1Api()
        return InstrumentedAPI(getattr(client, "%s%sApi" % (group, version))(api_client))


@api_stats_outputs.register("k8s")
class APIStats(DeltaStats):
    """Count kubernetes api calls by client method name, and their time."""

    def __init__(self, ctx, config=None):
        super().__init__(ctx, config)
        self.api_calls = Counter()
        self.api_time = 0.0

    def get_snapshot(self):
        return dict(self.api_calls)

    def get_metadata(self):
        return self.get_snapshot()

    def record(self, name, elapsed):
        self.api_calls[name] += 1
        self.api_time += elapsed

    def __enter__(self):
        _subscribers.append(self)
        self.push_snapshot()

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        _subscribers.remove(self)
        self.ctx.metrics.put_metric("ApiCalls", sum(self.api_calls.values()), "Count")
        self.ctx.metrics.put_metric("ApiTime", self.api_time, "Seconds")
        self.pop_snapshot()
