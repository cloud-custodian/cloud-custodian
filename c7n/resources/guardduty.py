# Copyright 2015-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.filters import ValueFilter, Filter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema
from c7n.actions import BaseAction
from botocore.exceptions import ClientError as BotoClientError


@resources.register('guardduty-invitations')
class GuardDutyInvitations(QueryResourceManager):
    """Filter GuardDuty invitation from trusted Master account id.

    :example:

    .. code-block:: yaml

            policies:
              - name: accept-trusted-guardduty-invitation
                resource: guardduty-invitations
                filters:
                  - AccountId: '000000000000'
    """

    class resource_type(object):
        service = 'guardduty'
        enum_spec = ('list_invitations', 'Invitations', None)
        id = 'InvitationId'
        name = 'Name'
        dimension = None


@resources.register('guardduty-detectors')
class GuardDutyDetectors(QueryResourceManager):

    class resource_type(object):
        service = 'guardduty'
        enum_spec = ('list_detectors', None, None)
        id = 'DetectorIds'
        name = 'DetectorIds'
        dimension = None


@GuardDutyInvitations.action_registry.register('accept-invitation')
class AcceptInvitation(BaseAction):
    """Filter GuardDuty invitation from trusted Master account id and accept it.

    :example:

    .. code-block:: yaml

            policies:
              - name: accept-trusted-guardduty-invitation
                resource: guardduty-invitations
                filters:
                  - AccountId: '000000000000'
                actions:
                  - type: accept-invitation
    """
    schema = type_schema(
        'accept-invitation', detectorid={'type': 'string'}, invitationid={'type': 'string'},
        masterid={'type': 'string'})
    permissions = ('guardduty:AcceptInvitation',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('guardduty')
        detectorids = client.list_detectors()['DetectorIds']
        if len(detectorids) == 0:
            detectorid = client.create_detector()['DetectorId']
        else:
            detectorid = detectorids[0]

        for r in resources:
            masterid = r['AccountId']
            invitationid = r['InvitationId']
            try:
                client.accept_invitation(DetectorId=detectorid,
                    InvitationId=invitationid, MasterId=masterid)
            except BotoClientError as e:
                self.log.exception('Exception: guardduty accept-invitation: %s',
                    e.response['Error']['Message'])
