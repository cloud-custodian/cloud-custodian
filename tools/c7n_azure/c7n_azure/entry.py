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
import c7n_azure.actions.base
import c7n_azure.actions.delete
import c7n_azure.actions.notify
import c7n_azure.actions.tagging
import c7n_azure.filters
import c7n_azure.output
import c7n_azure.policy
import c7n_azure.resources.cosmos_db
import c7n_azure.resources.key_vault
import c7n_azure.resources.key_vault_keys
import c7n_azure.resources.load_balancer
import c7n_azure.resources.resourcegroup
import c7n_azure.resources.public_ip
import c7n_azure.resources.storage
import c7n_azure.resources.sqlserver
import c7n_azure.resources.sqldatabase
import c7n_azure.resources.vm
import c7n_azure.resources.vnet
import c7n_azure.resources.route_table
import c7n_azure.resources.network_security_group
import c7n_azure.resources.web_app
import c7n_azure.resources.access_control
import c7n_azure.resources.network_interface
import c7n_azure.resources.disk
import c7n_azure.resources.cognitive_service
import c7n_azure.resources.data_factory
import c7n_azure.resources.iot_hub
import c7n_azure.resources.cdn
import c7n_azure.resources.container_registry
import c7n_azure.resources.container_service
import c7n_azure.resources.datalake_store
import c7n_azure.resources.redis
import c7n_azure.resources.vmss
import c7n_azure.resources.batch
import c7n_azure.resources.subscription
import c7n_azure.resources.policy_assignments
import c7n_azure.resources.image
import c7n_azure.resources.event_subscription
import c7n_azure.resources.appserviceplan  # noqa: F401


def initialize_azure():
    # after all resources are loaded, do out of band registrations of filters/actions
    resources.notify(resources.EVENT_FINAL)
    pass
