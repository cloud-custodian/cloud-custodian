# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""AWS Generic resource to process across all taggable resources."""

from collections import Counter
import itertools
from functools import partial

from botocore.exceptions import ClientError
from jsonschema import Draft7Validator as JsonSchemaValidator

from c7n.actions import Action
from c7n.config import Bag
from c7n.exceptions import PolicyValidationError, ResourceGroupTagError
from c7n.manager import resources
from c7n.resources.aws import Arn
from c7n import query
from c7n.utils import local_session


def _make_schema_item(props):
    return {"type": "object", "additionalProperties": False, "properties": props}


class DescribeTaggable(query.DescribeSource):

    schema = {
        "type": "array",
        "items": {
            "oneOf": [
                _make_schema_item({"non_compliant": {"type": "boolean"}}),
                _make_schema_item({"non_tagged": {"type": "boolean"}}),
                _make_schema_item({"verbose_errors": {"type": "boolean"}}),
                _make_schema_item(
                    {"resource_types": {"type": "array", "items": {"type": "string"}}}),
                _make_schema_item(
                    {"check_policy_tags": {"type": "array", "items": {"type": "string"}}}),
                _make_schema_item({
                    "with_tags": {
                        "type": "array", "items": _make_schema_item(
                            {'Key': {'type': 'string'},
                             'Values': {'type': 'array', 'items': {"type": "string"}}}
                        )
                    }
                })
            ]
        }
    }

    def get_params_tagging(self, query):
        params = {}
        if query.get('non_compliant'):
            params['IncludeComplianceDetails'] = True
            params['ExcludeCompliantResources'] = True
        if query.get('resource_types'):
            params['ResourceTypeFilters'] = query.resource_types
        if query.get('with_tags'):
            params['TagFilters'] = query.with_tags
        return params

    def get_params_explorer(self, query):
        parts = [
            f"region:{self.manager.config.region}",
            f"accountid:{self.manager.config.account_id}",
            "tag:none",
        ]

        if query.get('resource_types'):
            for rt in query.resource_types:
                parts.append(f'resourcetype:{rt}')
        else:
            parts.append("resourcetype.supports:tags")
        params = {'Filters': {'FilterString': " ".join(parts)}}

        return params

    def check_policy_key_matches(self, client, query):
        if not query.get('check_policy_tags'):
            return True
        if not query.non_compliant:
            return True

        response = client.list_required_tags()
        required = set(
            itertools.chain.from_iterable(
                [rt['ReportingTagKeys'] for rt in response['RequiredTags']]
            )
        )
        expected = set(query.check_policy_tags)
        return not bool(expected.difference(required))

    def resources(self, query):
        query = Bag(query)
        session = local_session(self.manager.session_factory)
        client = session.client('resourcegroupstaggingapi')
        pager = client.get_paginator('get_resources')
        results = []

        if not self.check_policy_key_matches(client, query):
            self.manager.log.critical(
                "policy tags dont match organization tag policy in effect account %s" % (
                    self.manager.config.account_id
                )
            )
            return results

        for page in pager.paginate(**self.get_params_tagging(query)):
            results.extend(page.get('ResourceTagMappingList', []))

        tcount = len(results)
        self.manager.log.debug("resourcegrouptagging resources %d" % tcount)
        if not ('with_tags' not in query and 'non_tagged' in query):
            return results

        client = session.client('resource-explorer-2')
        pager = client.get_paginator("list_resources")
        ids = {r['ResourceARN'] for r in results}
        normalize = partial(self.normalize_explorer_results, query=query)

        try:
            for page in pager.paginate(**self.get_params_explorer(query)):
                results.extend(
                    [r for r in normalize(page.get("Resources", []))
                     if r['ResourceARN'] not in ids]
                )
        except ClientError as e:
            # a default view without tags included in the index OR an account missing a default view
            if e.response.get('Error', {}).get('Code') == 'ValidationException':
                self.manager.log.critical(
                    "resource explorer account:%s region:%s misconfigured default view" % (
                        self.manager.config.account_id,
                        self.manager.config.region
                    )
                )
            else:
                raise
        self.manager.log.debug("resource-explorer resources %d" % (len(results) - tcount))
        return results

    def normalize_explorer_results(self, exp2_batch, query=None):
        page = []
        compliance = {}
        skipped = Counter()

        if query and query.get('non_compliant'):
            compliance = {'ComplianceStatus': False}
            compliance['MissingTagKeys'] = query.get('check_policy_tags', [])

        for r in exp2_batch:
            if r['ResourceType'] in EXPLORER_NO_TAG_SUPPORT:
                skipped[r['ResourceType']] += 1
                continue
            e_tags = [p['Data'] for p in r['Properties'] if p['Name'] == 'tags']
            if not e_tags:
                r_tags = []
            else:
                r_tags = e_tags[0]

            page.append(
                dict(
                    ResourceARN=r['Arn'],
                    Tags=r_tags,
                    OwningAccountId=r['OwningAccountId'],
                    ResourceType=r['ResourceType'],
                    LastReportedAt=r['LastReportedAt'],
                    ComplianceDetails=compliance
                )
            )

        if skipped:
            self.manager.log.debug('Skipped non taggable explorer resources  %s' % skipped)
        return page

    def get_query_params(self, query_params):
        query = dict(query_params or [])
        for item in self.manager.data.get('query'):
            query.update(item)
        return query


EXPLORER_NO_TAG_SUPPORT = set("""\
apigateway:apis/integrations
apigateway:apis/routes
apigateway:restapis/deployments
apigateway:restapis/resources
apigateway:restapis/resources/methods
autoscaling:autoScalingGroup
cloudfront:cache-policy
cloudfront:continuous-deployment-policy
cloudfront:field-level-encryption-config
cloudfront:field-level-encryption-profile
cloudfront:function
cloudfront:origin-access-control
cloudfront:origin-access-identity
cloudfront:origin-request-policy
cloudfront:realtime-log-config
cloudfront:response-headers-policy
cloudwatch:dashboard
eks:daemonset
eks:deployment
eks:endpointslice
eks:ingress
eks:namespace
eks:persistentvolume
eks:replicaset
eks:service
eks:statefulset
elasticache:globalreplicationgroup
events:api-destination
events:archive
events:connection
events:endpoint
globalaccelerator:accelerator/listener
globalaccelerator:accelerator/listener/endpoint-group
glue:table
iam:group
iot:cert
iot:ruledestination
iot:thing
iottwinmaker:workspace
iottwinmaker:workspace/component-type
iottwinmaker:workspace/entity
iottwinmaker:workspace/sync-job
kafka:configuration
ivschat:logging-configuration
kendra:index/access-control-configuration
kendra:index/experience
lambda:function/version
lambda:layer/version
macie2:allow-list
macie2:custom-data-identifier
macie2:findings-filter
macie2:member
mediaconnect:gateway
partnercentral:catalog/engagement
partnercentral:catalog/engagement-invitation
partnercentral:resourcesnapshot
personalize:schema
resource-explorer-2:index
resource-explorer-2:view
route53-recovery-control:controlpanel/routingcontrol
s3:multiregionaccesspoint
sagemaker:human-loop
sagemaker:image-version
ssm:resource-data-sync
ssm:windowtarget
ssm:windowtask
wafv2:ipset
wafv2:regexpatternset
wafv2:rulegroup
wafv2:webacl
""".split('\n'))


@resources.register("taggable")
class Taggable(query.QueryResourceManager):
    """An abstract resource type that represents any taggable resource
    in AWS. Utilizes server side querying wherever possible via
    resource group tagging and resource-explorer-2 apis to provide for
    efficient query of non compliant and non tagged resources, while also
    providing for bulk tagging operations on those resources.

    This primarily relies on server side queries against these two
    services to effect functionality, as such the functionality is
    mostly exposed via the policy `query` block which is
    required.

    Additionally there are pre-requisites for account enablement of
    those two services to be able to use this resource, a service
    linked role for resource-explorer, and a default view must be
    available. For resource group tagging an organizations tag policy
    for non_compliant resource querying active on account. note, the
    tag policy only needs to be in reporting mode. Due to org policy
    tag policy size limits, it may be needed to multiplex for enforcement
    across all taggable resource types.

    *Note* Disabled services, due to inconsistencies with the resource
    group tagging api and resource-explorer-2 apis we disable
    autoscaling. As resource-explorer-2 apis don't include them in the
    filter (resource:supports:tags) because even though they have tags,
    resource-explorer does not fetch them.

    Its required to use a separate custodian resource type specific
    policy for the following services.

    .. code-block:: yaml

      policies:
         - name: non-compliant
           resource: aws.taggable
           query:
            - non_compliant: true
            - non_tagged: true
            - check_policy_tags: ["Owner"]


    `non_compliant` (boolean) utilizes the reporting of an applied organization tag
    policy in affect against the account/region to determine resources that
    are non compliant. `check_policy_tags` provides a sanity check of the
    policy authors expectation of the tags being checked, and is verified
    against what's actually in the account.

    `check_policy_tags` allows specifying an array of tag keys that will
    be validated against the organization tag policies in affect on
    the account. if the specified tag keys are not part of the org tag
    policy being enforced on the account resources and the custodian policy is
    searching for non_compliant resources, no resources will be
    returned. This is intended to prevent against mismatches of required tags
    actually in effect against the account. However tag policies are applied
    to individual resources, and this check is against the union of all required
    keys for any resource.

    `non_tagged` (boolean) enables the use of resource-explorer to supplement the
    results with resources that have never been tagged. It is safe to run
    against explorer aggregator accounts, as it scopes to only resources
    within an account. Note resource explorer does not support tag based
    searching for iam roles or users, so iam resources that have no tags
    will require a separate policy.

    `verbose_errors` (boolean) when performing tag actions against discovered
    resources, some resources may not support resource group tagging. By default
    the service and the resource count are reported back. Enabling this logs
    a line per resource with the specific error message.

    `resource_types` is to scope the check to particular resources
    types, default is against all taggable resources. Note the values
    here are represented by those used by the tagging / resource
    explorer services.

    See the table here for vocabulary
    https://docs.aws.amazon.com/resource-explorer/latest/userguide/supported-resource-types.html

    `with_tags` represents a server side filter to only return results
    matching resources with a particular set of tags and tag values.


    .. code-block:: yaml

      policies:
         - name: non-compliant
           resource: aws.taggable
           query:
            - resource_types: [ec2:instance, ec2:security-group]
            - with_tags:
               - Key: App
               - Values: [Apple, Orange, Grapefruit]


    The example above will only return ec2 instances and security groups
    with any of the three defined values for the App tag.

    """

    source_mapping = {"describe": DescribeTaggable}

    class resource_type(query.TypeInfo):
        id = 'ResourceARN'
        filter_name = None
        service = 'resourcegrouptagging'
        name = 'ResourceARN'
        arn = name
        permission_prefix = "tag"
        universal_taggable = object()

    def get_permissions(self):
        return ("tag:GetResources", "resource-explorer-2:Search",)

    def validate(self):
        if 'query' not in self.data:
            raise PolicyValidationError(
                "taggable resource requires the use of a `query` block, see docs"
            )
        validator = JsonSchemaValidator(DescribeTaggable.schema)
        errors = list(validator.iter_errors(self.data['query']))
        if errors:
            raise PolicyValidationError(
                "taggable resource query misconfiguration %s" % errors
            )


class TagActionDispatch(Action):

    override_actions = {
        ('apigateway', 'stage'): None,
        ('cassandra', 'keyspace'): None,
        ('ssm', 'managed-instance'): None,
        ('bedrock', 'agent'): None,
        ('bedrock', 'agent-alias'): None,
        ('s3express', 'bucket'): None,
        ('ecs', 'task'): None,
        # ('cloudformation', 'stack'): None,
        ('memorydb', 'parametergroup'): None,
        ('autoscaling', 'autoScalingGroup'): 'aws.asg'
    }

    concurrency = 1

    def process_overrides(self, service, rset):
        """Handle specific resource types where we have native support
        when resource group tagging doesn't support modification.
        """
        arn = Arn.parse(rset[0]['ResourceARN'])

        spec_map = self.get_tag_spec()
        if arn.service == 'apigateway':
            for r in list(rset):
                if '/stages/' in r['ResourceARN']:
                    rset.remove(r)
        elif arn.resource_type.startswith('autoScalingGroup'):
            asg_set = []
            for r in rset:
                asg_set.append({
                    'AutoScalingGroupArn': r,
                    # implied dep on implicit Arn parse behavior
                    'AutoScalingGroupName': Arn.parse(r['ResourceARN']).resource
                })
            manager = self.manager.get_resource_manager(
                'aws.asg',
                {'name': 'asg-taggable',
                 'resource': 'aws.asg',
                 'actions': [{
                     'type': 'tag',
                     # implied default :/
                     'propogate': True,
                     'tags': spec_map}]}
            )
            manager.actions[0].process(asg_set)
            return True
        elif arn.service == 'bedrock':
            for r in list(rset):
                # throws an invalid resource arn error against resource group tagging
                if Arn.parse(r['ResourceARN']).resource_type in (
                        'agent-alias', 'agent', 'knowledge-base'):
                    rset.remove(r)
        elif arn.service == 'cassandra':
            for r in list(rset):
                if ':/keyspace/' in r['ResourceARN']:
                    rset.remove(r)
        elif arn.service == 'ecs':
            for r in list(rset):
                if ":task/" in r['ResourceARN']:
                    rset.remove(r)
        elif arn.service == 'memorydb':
            for r in list(rset):
                if 'parametergroup/default.' in r['ResourceARN']:
                    rset.remove(r)
        elif arn.service == 's3express':
            for r in list(rset):
                if ":bucket/" in r['ResourceARN']:
                    rset.remove(r)
        elif arn.service == 'ssm':
            for r in list(rset):
                # throws an error if the prefix is not mi-
                if 'managed-instance/i-' in r['ResourceARN']:
                    rset.remove(r)
        return False

    def process(self, resources):
        stats = Counter()
        service_batches = {}
        override_services = {s[0] for s in self.override_actions.keys()}

        for r in resources:
            rarn = Arn.parse(r['ResourceARN'])
            stats[rarn.service] += 1
            service_batches.setdefault(rarn.service, []).append(r)

        verbose = bool([item for item in self.manager.data['query'] if item.get('verbose_errors')])

        self.manager.log.debug("Grouped by resources %s" % sorted(stats.items()))
        for s, rset in sorted(service_batches.items()):
            self.manager.log.debug("bulk tag service:%s resources:%d" % (s, len(rset)))
            if s in override_services:
                if self.process_overrides(s, rset):
                    continue
            try:
                super().process(rset)
            except ResourceGroupTagError as e:
                self.manager.log.error(
                    (f"resource group api error op:{e.operation_name} "
                     f"on service:{s} with {len(e.errors)} failed resources")
                )
                if verbose:
                    for r_arn, err in e.errors.items():
                        self.manager.log.error(
                            f"resource {r_arn} code:{err['ErrorCode']} msg:{err['ErrorMessage']}"
                        )


Taggable.action_registry.register(
    'tag',
    type('TaggableTag', (TagActionDispatch, Taggable.action_registry['tag']), {})
)

Taggable.action_registry.register(
    'remove-tag',
    type('TaggableRemoveTag', (TagActionDispatch, Taggable.action_registry['remove-tag']), {})
)
