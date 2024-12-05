# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query
from c7n.utils import local_session


class DescribeGuarddutyFinding(query.DescribeSource):
    def resources(self, query):
        detector_id = self.get_detector_id()
        if not detector_id:
            return ()
        if not query:
            query = {}
        query['DetectorId'] = detector_id
        self.manager.resource_type.batch_detail_spec[-1] = {'DetectorId': detector_id}
        return super().resources(query)

    def get_detector_id(self):
        client = local_session(self.manager.session_factory).client('guardduty')
        ids = client.list_detectors().get('DetectorIds')
        return ids and ids[0] or ids


@resources.register("guardduty-finding")
class GuarddutyFinding(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "guardduty"
        enum_spec = ('list_findings', 'FindingIds', None)
        batch_detail_spec = ['get_findings', 'FindingIds', None, 'Findings', None]
        arn_type = "finding"
        arn = "Arn"
        id = "AccountId"
        name = "Description"

    source_mapping = {
        "describe": DescribeGuarddutyFinding,
    }
