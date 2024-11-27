# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

from c7n.actions import BaseAction, Action
from c7n.filters.iamaccess import CrossAccountAccessFilter
import c7n.filters.policystatement as polstmt_filter
from c7n.exceptions import PolicyValidationError
from c7n.manager import resources
from c7n.query import DescribeSource, QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema, format_string_values
from c7n.tags import universal_augment


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
