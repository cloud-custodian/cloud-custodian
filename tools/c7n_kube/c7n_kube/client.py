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

from kubernetes import config, client
from kubernetes.client import Configuration, ApiClient

from c7n.output import APICallStats, api_stats_outputs, record_api_call

log = logging.getLogger("custodian.k8s.client")


class InstrumentedAPI:
    """Wraps a kubernetes api object (e.g. CoreV1Api) to record each public
    method call, by method name, with its duration."""

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
                record_api_call(name, time.perf_counter() - start)

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
class APIStats(APICallStats):
    """Count kubernetes api calls by client method name, and their time."""
