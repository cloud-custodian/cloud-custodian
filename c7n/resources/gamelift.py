# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
