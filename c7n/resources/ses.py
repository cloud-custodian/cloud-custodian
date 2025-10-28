# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import logging

from c7n.actions import BaseAction, Action
from c7n.filters.iamaccess import CrossAccountAccessFilter
import c7n.filters.policystatement as polstmt_filter
from c7n.exceptions import PolicyValidationError
from c7n.manager import resources
from c7n.query import DescribeSource, QueryResourceManager, TypeInfo, DescribeWithResourceTags
from c7n.utils import local_session, type_schema, format_string_values
from c7n.tags import universal_augment
from c7n.tags import RemoveTag, Tag
from c7n.filters import (FilterRegistry, ListItemFilter)

filters = FilterRegistry('SESIngressEndpoint.filters')

log = logging.getLogger("custodian.ses")


class DescribeConfigurationSet(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('ses')
        for r in resources:
            details = client.describe_configuration_set(ConfigurationSetName=r['Name'],
                ConfigurationSetAttributeNames=[
                    'eventDestinations',
                    'trackingOptions',
                    'deliveryOptions',
                    'reputationOptions'
                ]
            )
            r.update({
                k: details[k]
                for k in details
                if k not in {'ConfigurationSet', 'ResponseMetadata'}
            })
        return universal_augment(self.manager, resources)


@resources.register('ses-configuration-set')
class SESConfigurationSet(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'ses'
        enum_spec = ('list_configuration_sets', 'ConfigurationSets', None)
        name = id = 'Name'
        arn_type = 'configuration-set'
        universal_taggable = object()
        config_type = "AWS::SES::ConfigurationSet"
        permissions_augment = ("ses:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeConfigurationSet
    }


class DescribeConfigurationSetV2(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('sesv2')
        resource_list = []
        for r in resources:
            details = client.get_configuration_set(ConfigurationSetName=r)
            resource_list.append({
                k: details[k]
                for k in details
                if k not in {'ResponseMetadata'}
            })
        return universal_augment(self.manager, resource_list)


@resources.register('ses-configuration-set-v2')
class SESConfigurationSetV2(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'sesv2'
        enum_spec = ('list_configuration_sets', 'ConfigurationSets', None)
        name = id = 'ConfigurationSetName'
        arn_service = 'ses'
        arn_type = 'configuration-set'
        universal_taggable = object()
        config_type = "AWS::SES::ConfigurationSet"
        permission_prefix = 'ses'
        permissions_augment = ("ses:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeConfigurationSetV2
    }


@SESConfigurationSet.action_registry.register('set-delivery-options')
class SetDeliveryOptions(BaseAction):
    """Set the TLS policy for ses

    :example:

    .. code-block:: yaml

            policies:
              - name: ses-set-delivery-options-require
                resource: ses-configuration-set
                filters:
                  - type: value
                    key: DeliveryOptions.TlsPolicy
                    op: eq
                    value: Optional
                actions:
                  - type: set-delivery-options
                    tls-policy: Require
    """

    schema = type_schema(
        'set-delivery-options',
        required=['tls-policy'],
        **{"tls-policy": {'enum': ['Require', 'Optional']}},
    )
    permissions = ("ses:PutConfigurationSetDeliveryOptions",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ses')
        tls_policy = self.data.get('tls-policy')
        for r in resources:
            client.put_configuration_set_delivery_options(
                ConfigurationSetName=r['Name'],
                DeliveryOptions={
                    'TlsPolicy': tls_policy
                },
            )


@SESConfigurationSet.action_registry.register('delete')
class DeleteSESConfigurationSet(Action):
    """Delete an SES Configuration Set resource.

    :example:

    .. code-block:: yaml

            policies:
              - name: ses-delete-configuration-set
                resource: aws.ses-configuration-set
                actions:
                    - delete

    """
    schema = type_schema('delete')
    permissions = ("ses:DeleteConfigurationSet",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ses')
        for resource in resources:
            self.manager.retry(
                client.delete_configuration_set,
                ConfigurationSetName=resource['Name'],
                ignore_err_codes=("ConfigurationSetDoesNotExistException",)
            )


@resources.register('ses-email-identity')
class SESEmailIdentity(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'sesv2'
        enum_spec = ('list_email_identities', 'EmailIdentities', None)
        detail_spec = ('get_email_identity', 'EmailIdentity', 'IdentityName', None)
        name = id = 'IdentityName'
        arn_service = 'ses'
        arn_type = 'identity'
        universal_taggable = object()
        permission_prefix = 'ses'
        arn_service = 'ses'
        cfn_type = 'AWS::SES::EmailIdentity'


@SESEmailIdentity.filter_registry.register('cross-account')
class CrossAccountEmailIdentityFilter(CrossAccountAccessFilter):

    # dummy permission
    permissions = ('ses:ListEmailIdentities',)
    policy_attribute = 'Policies'

    def __call__(self, r):
        policies = self.get_resource_policy(r)
        if policies is None:
            return False
        resource_violations = {}
        for policy_name, policy in policies.items():
            violations = self.checker.check(policy)
            if violations:
                resource_violations[policy_name] = violations
        if resource_violations:
            r[self.annotation_key] = resource_violations
            return True


@SESEmailIdentity.filter_registry.register('has-statement')
class HasStatementFilter(polstmt_filter.HasStatementFilter):

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.policy_attribute = 'Policies'

    def get_std_format_args(self, email_identity):
        return {
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region,
            'email_identity_name': email_identity['IdentityName'],
        }

    def process_resource(self, email_identity):
        policies = email_identity.get(self.policy_attribute)
        if not policies:
            return None

        for policy in policies.values():
            p = json.loads(policy)

            required = list(self.data.get('statement_ids', []))
            statements = p.get('Statement', [])
            for s in list(statements):
                if s.get('Sid') in required:
                    required.remove(s['Sid'])

            required_statements = format_string_values(list(self.data.get('statements', [])),
                                                       **self.get_std_format_args(email_identity))

            for required_statement in required_statements:
                for statement in statements:
                    found = 0
                    for key, value in required_statement.items():
                        if key in ['Action', 'NotAction']:
                            if key in statement and self.action_resource_case_insensitive(value) \
                               == self.action_resource_case_insensitive(statement[key]):
                                found += 1
                        else:
                            if key in statement and value == statement[key]:
                                found += 1
                    if found and found == len(required_statement):
                        required_statements.remove(required_statement)
                        break

            if (self.data.get('statement_ids', []) and not required) or \
               (self.data.get('statements', []) and not required_statements):
                return email_identity


@SESEmailIdentity.action_registry.register('remove-policies')
class RemoveIdentityPolicy(BaseAction):
    """
    Action to remove policies from an SES Email Identity

    :example:

    .. code-block:: yaml

        policies:
          - name: ses-remove-policy
            resource: aws.ses-email-identity
            filters:
              - type: cross-account
            actions:
              - type: remove-policies
                policy_names: matched
    """
    schema = type_schema('remove-policies', required=['policy_names'],
        policy_names={'oneOf': [
            {'enum': ['matched', "*"]},
            {'type': 'array', 'items': {'type': 'string'}}]})

    permissions = ('ses:DeleteEmailIdentityPolicy',)
    policy_attribute = 'Policies'

    def validate(self):
        if self.data.get('policy_names') == 'matched':
            for f in self.manager.iter_filters():
                if isinstance(f, CrossAccountEmailIdentityFilter):
                    return self
            raise PolicyValidationError(
                '`remove-policies` may only be used on `matched` policy_names '
                'in conjunction with `cross-account` filter on %s' %
                (self.manager.data,)
            )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('sesv2')
        policy_names = self.data.get('policy_names', [])
        for r in resources:
            policies_to_remove = []
            if isinstance(policy_names, list):
                policies_to_remove = policy_names
            else:
                if policy_names == "*":
                    policies_to_remove = r.get(self.policy_attribute, {}).keys()
                elif policy_names == "matched":
                    policies_to_remove = r.get(
                        CrossAccountEmailIdentityFilter.annotation_key, {}
                    ).keys()

            for policy in policies_to_remove:
                self.manager.retry(
                    client.delete_email_identity_policy,
                    EmailIdentity=r['IdentityName'],
                    PolicyName=policy,
                )


@resources.register('ses-receipt-rule-set')
class SESReceiptRuleSet(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'ses'
        enum_spec = ('list_receipt_rule_sets', 'RuleSets', None)
        detail_spec = ('describe_receipt_rule_set', 'RuleSetName', 'Name', None)
        name = id = 'Name'
        arn_type = 'receipt-rule-set'


@SESReceiptRuleSet.action_registry.register('delete')
class Delete(Action):
    """Delete an SES Receipt Rule Set resource.

    :example:

    .. code-block:: yaml

            policies:
              - name: ses-delete-rule-set
                resource: aws.ses-receipt-rule-set
                filters:
                  - type: value
                    key: Rules[0].Enabled
                    op: eq
                    value: true
                actions:
                    - delete

    """
    schema = type_schema('delete')
    permissions = ("ses:DeleteReceiptRuleSet",)

    def process(self, rulesets):
        client = local_session(self.manager.session_factory).client('ses')
        for ruleset in rulesets:
            self.manager.retry(
                client.delete_receipt_rule_set,
                RuleSetName=ruleset["Metadata"]['Name'],
                ignore_err_codes=("CannotDeleteException",)
            )


class DescribeDedicatedIpPool(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('sesv2')
        resource_list = []
        # Default & Shared Dedicated IP pool names
        # https://docs.aws.amazon.com/ses/latest/dg/managing-ip-pools.html
        default_shared_pools = ["ses-default-dedicated-pool", "ses-shared-pool"]
        for r in resources:
            if r in default_shared_pools:
                # For default & shared pools, we cannot call get_dedicated_ip_pool
                log.info("Skipping default/shared pool: %s", r)
                continue
            details = client.get_dedicated_ip_pool(PoolName=r)
            resource_list.append(details["DedicatedIpPool"])
        return universal_augment(self.manager, resource_list)


@resources.register('ses-dedicated-ip-pool')
class SESDedicatedIpPool(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'sesv2'
        enum_spec = ('list_dedicated_ip_pools', 'DedicatedIpPools', None)
        name = id = 'PoolName'
        arn_service = 'ses'
        arn_type = 'dedicated-ip-pool'
        universal_taggable = object()
        config_type = None
        permission_prefix = 'ses'
        permissions_augment = ("ses:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeDedicatedIpPool
    }


@resources.register('ses-ingress-endpoint')
class SESIngressEndpoint(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'mailmanager'
        enum_spec = ('list_ingress_points', 'IngressPoints', None)
        detail_spec = ('get_ingress_point', 'IngressPointId', 'IngressPointId', None)
        name = 'IngressPointName'
        id = 'IngressPointId'
        arn_type = 'mailmanager-ingress-point'
        arn = 'IngressPointArn'
        config_type = "AWS::SES::MailManagerIngressPoint"
        permission_prefix = 'ses'

    source_mapping = {
        'describe': DescribeWithResourceTags
    }


@SESIngressEndpoint.action_registry.register('tag')
class TagSESIngressEndpoint(Tag):
    """Create tags on SES Ingress Endpoint

    :example:

    .. code-block:: yaml

        policies:
            - name: ses-ingress-endpoint-tag
              resource: aws.ses-ingress-endpoint
              actions:
                - type: tag
                  key: test
                  value: something
    """
    permissions = ('ses:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        for r in resources:
            client.tag_resource(ResourceArn=r["IngressPointArn"], Tags=new_tags)


@SESIngressEndpoint.action_registry.register('remove-tag')
class RemoveTagSESIngressEndpoint(RemoveTag):
    """Remove tags from a SES Ingress Endpoint
    :example:

    .. code-block:: yaml

        policies:
            - name: ingress-endpoint-remove-tag
              resource: aws.ses-ingress-endpoint
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('ses:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(ResourceArn=r['IngressPointArn'], TagKeys=tags)


@SESIngressEndpoint.action_registry.register('delete')
class DeleteSESIngressEndpoint(Action):
    """Delete an SES Ingress Endpoint resource.

    :example:

    .. code-block:: yaml

            policies:
              - name: ses-delete-ingress-endpoint
                resource: aws.ses-ingress-endpoint
                actions:
                    - delete

    """
    schema = type_schema('delete')
    permissions = ("ses:DeleteIngressPoint",)

    def process(self, ingressendpoints):
        client = local_session(self.manager.session_factory).client('mailmanager')
        for ingressendpoint in ingressendpoints:
            self.manager.retry(
                client.delete_ingress_point,
                IngressPointId=ingressendpoint["IngressPointId"],
                ignore_err_codes=("ResourceNotFoundException",)
            )


@SESIngressEndpoint.filter_registry.register('rule-set')
class SESIngressEndpointRuleSet(ListItemFilter):
    """Filter for SES Ingress Endpoints to look at rule sets

    The schema to supply to the attrs follows the schema here:
     https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/mailmanager/client/get_rule_set.html

    :example:

    .. code-block:: yaml

            policies:
              - name: ses-ingress-endpoint-rule-set
                resource: ses-ingress-endpoint
                filters:
                - or:
                  - not:
                    - type: rule-set
                      attrs:
                        - type: value
                          key: length(Actions[]|[?Archive])
                          value: 1
                  - type: rule-set
                    attrs:
                      - type: value
                        key: "length(Actions[]|[?Archive.TargetArchive \
                            .Retention.RetentionPeriodInMonth > `5`])"
                        value: 1
    """
    schema = type_schema(
        'rule-set',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    permissions = ("ses:GetRuleSet",)
    annotation_key = 'RuleSet'
    annotate_items = True

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.data['key'] = self.annotation_key

    def get_item_values(self, resource):
        if self.annotation_key not in resource:
            client = local_session(self.manager.session_factory).client('mailmanager')
            response = client.get_rule_set(RuleSetId=resource['RuleSetId'])
            resource["RuleSetName"] = response["RuleSetName"]
            resource["RuleSetArn"] = response["RuleSetArn"]
            rules = response.get('Rules', [])
            for rule in rules:
                for action in rule.get("Actions", []):
                    if "Archive" in action:
                        target_archive = action["Archive"]["TargetArchive"]
                        archive_details = client.get_archive(ArchiveId=target_archive)
                        archive_details.pop("ResponseMetadata")
                        # Convert retention period to numeric values for easier comparison
                        action["Archive"]["TargetArchive"] = \
                            self.convert_retention_period(archive_details)
            resource[self.annotation_key] = rules

        return resource[self.annotation_key]

    def convert_retention_period(self, archive_details):
        retention_mapping = {
            "THREE_MONTHS": 3,
            "SIX_MONTHS": 6,
            "NINE_MONTHS": 9,
            "ONE_YEAR": 12,
            "EIGHTEEN_MONTHS": 18,
            "TWO_YEARS": 24,
            "THIRTY_MONTHS": 30,
            "THREE_YEARS": 36,
            "FOUR_YEARS": 48,
            "FIVE_YEARS": 60,
            "SIX_YEARS": 72,
            "SEVEN_YEARS": 84,
            "EIGHT_YEARS": 96,
            "NINE_YEARS": 108,
            "TEN_YEARS": 120,
            "PERMANENT": 99999  # Very large value to represent "PERMANENT"
        }

        retention_text = archive_details["Retention"].get("RetentionPeriod")
        retention_value = retention_mapping.get(retention_text, None)  # Map to numeric value
        archive_details["Retention"]["RetentionPeriodInMonth"] = retention_value
        return archive_details
