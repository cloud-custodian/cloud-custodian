# Copyright 2016-2017 Capital One Services, LLC
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
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo


@resources.register('gamelift-build')
class GameLiftBuild(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'gamelift'
        enum_spec = ('list_builds', 'Builds', None)
        id = 'BuildId'
        name = 'Name'
        date = 'CreationTime'
        arn = False
        cfn_type = 'AWS::GameLift::Build'


@resources.register('gamelift-fleet')
class GameLiftFleet(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'gamelift'
        enum_spec = ('list_fleets', 'FleetIds', None)
        id = 'FleetId'
        arn = "FleetArn"
        name = 'Name'
        date = 'CreationTime'
        batch_detail_spec = (
            "describe_fleet_attributes", "FleetIds", None, "FleetAttributes", None)
        cfn_type = 'AWS::GameLift::Fleet'
