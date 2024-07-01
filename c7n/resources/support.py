# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters import Filter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.utils import local_session, get_support_region, type_schema


@resources.register('support-case')
class SupportCase(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'support'
        enum_spec = ('describe_cases', 'cases', None)
        global_resource = True
        filter_name = 'caseIdList'
        filter_type = 'list'
        id = 'caseId'
        name = 'displayId'
        date = 'timeCreated'
        arn = False

    def get_client(self):
        region = get_support_region(self)
        return local_session(self.session_factory).client('support', region_name=region)


class DescribeAdvisorCheck(DescribeSource):
    def resources(self, query):
        if not query:
            query = {'language': 'en'}
        return super().resources(query)


@resources.register("advisor-check")
class AdvisorCheck(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "support"
        enum_spec = ('describe_trusted_advisor_checks', 'checks', None)
        detail_spec = ('describe_trusted_advisor_check_result', 'checkId', 'id', 'result')
        arn_type = "checks"
        arn_service = "trustedadvisor"
        name = id = "checkId"
        universal_taggable = object()

    source_mapping = {
        "describe": DescribeAdvisorCheck,
    }


@AdvisorCheck.filter_registry.register('resource-status')
class StatusErrorFilter(Filter):
    """Filter Trusted Advisor flagged resources that match specific statuses

    This filter operates on both the high level (alert) status as well as the status of
    all resources evaluated.  In other words, if an alert status is set to 'error', it
    may contain resources that have a status of 'ok'.  This filter can be used to only
    return resources that have a status of error.  For example:

    :example:

    .. code-block:: yaml

        policies:
          - name: trusted-advisor-errors
            resource: advisor-check
            filters:
              - type: resource-status
                statuses:
                  - error

    """
    schema = type_schema('resource-status',
        required=['statuses'],
        statuses={'type': 'array', 'items': {'enum':
            ['ok', 'warning', 'error', 'not_available']}})

    def process(self, resources, event=None):
        filtered_resources = []
        for resource in resources:
            if resource['status'] in self.data.get('statuses'):
                if resource.get('flaggedResources'):
                    flaggedResources = self.has_status(resource)
                    resource["flaggedResources"] = flaggedResources
                filtered_resources.append(resource)
        return filtered_resources

    def has_status(self, r):
        flaggedResources = [
            fr for fr in r['flaggedResources'] if fr["status"] in self.data['statuses']
        ]
        return flaggedResources
