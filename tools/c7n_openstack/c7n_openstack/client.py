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

import openstack


log = logging.getLogger('custodian.openstack.client')


class Session:
    def __init__(self):
        self.http_proxy = os.getenv('HTTPS_PROXY')
        self.cloud_name = os.getenv('OS_CLOUD_NAME')

    def client(self):
        if self.cloud_name:
            log.debug(f"Connect to OpenStack cloud {self.cloud_name}")
        else:
            log.debug(("OpenStack cloud name not set, "
                       "try to get openstack credential from environment"))
        cloud = openstack.connect(cloud=self.cloud_name)
        return cloud
