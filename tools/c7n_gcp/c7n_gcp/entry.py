# Copyright 2018 Capital One Services, LLC
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

import logging

import c7n_gcp.policy

# This is an alphabetically sorted import list
import c7n_gcp.resources.bigquery
import c7n_gcp.resources.build
import c7n_gcp.resources.cloudbilling
import c7n_gcp.resources.compute
import c7n_gcp.resources.dataflow
import c7n_gcp.resources.deploymentmanager
import c7n_gcp.resources.dns
import c7n_gcp.resources.function
import c7n_gcp.resources.gke
import c7n_gcp.resources.iam
import c7n_gcp.resources.loadbalancer
import c7n_gcp.resources.logging
import c7n_gcp.resources.mlengine
import c7n_gcp.resources.network
import c7n_gcp.resources.pubsub
import c7n_gcp.resources.resourcemanager
import c7n_gcp.resources.service
import c7n_gcp.resources.source
import c7n_gcp.resources.spanner
import c7n_gcp.resources.storage
import c7n_gcp.resources.sql  # noqa: F401


from c7n_gcp.provider import resources as gcp_resources

logging.getLogger('googleapiclient.discovery').setLevel(logging.WARNING)

# Let resource registry subscribers have a chance to look at full set of resources.
gcp_resources.notify(gcp_resources.EVENT_FINAL)


def initialize_gcp():
    pass
