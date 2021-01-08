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

from kubernetes import config, client
from kubernetes.client import Configuration, ApiClient

log = logging.getLogger('custodian.k8s.client')


class Session:
    def __init__(self, config_file=None):
        self.config_file = config_file
        self.http_proxy = os.getenv('HTTPS_PROXY')

    def client(self, group, version):
        client_config = Configuration()
        config.load_kube_config(self.config_file, client_configuration=client_config)
        client_config.proxy = self.http_proxy
        api_client = ApiClient(configuration=client_config)
        log.debug('connecting to %s' % (api_client.configuration.host))
        # e.g. client.CoreV1Api()
        return getattr(client, '%s%sApi' % (group, version))(api_client)
