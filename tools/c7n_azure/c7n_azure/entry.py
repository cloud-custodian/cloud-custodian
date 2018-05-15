# Copyright 2017-2018 Capital One Services, LLC
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

from c7n_azure.provider import resources
import c7n_azure.actions
import c7n_azure.resources.cosmos_db
import c7n_azure.resources.key_vault
import c7n_azure.resources.load_balancer
import c7n_azure.resources.resourcegroup
import c7n_azure.resources.public_ip
import c7n_azure.resources.storage
import c7n_azure.resources.sqlserver
import c7n_azure.resources.vm
import c7n_azure.resources.vnet
import c7n_azure.resources.network_security_group
import c7n_azure.resources.web_app  # noqa: F401


def initialize_azure():
    # after all resources are loaded, do out of band registrations of filters/actions
    resources.notify(resources.EVENT_FINAL)
    pass
