# Copyright 2019 Capital One Services, LLC
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

from c7n_kube.actions.core import DeleteResource, PatchResource
from c7n_kube.actions.labels import LabelAction
from c7n_kube.provider import resources as kube_resources

SHARED_ACTIONS = (DeleteResource, LabelAction, PatchResource)


for action in SHARED_ACTIONS:
    kube_resources.subscribe(kube_resources.EVENT_REGISTER, action.register_resources)
