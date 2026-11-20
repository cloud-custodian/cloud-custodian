# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import PolicyValidationError
from c7n.utils import type_schema

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import ChildResourceManager, ChildTypeInfo


@resources.register('billing-budget')
class BillingBudget(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/billing/docs/reference/budget/rest/v1/billingAccounts.budgets

    Example::

        policies:
          - name: gcp-billing-budget-no-last-period-amount
            resource: gcp.billing-budget
            filters:
              - type: value
                key: amount.lastPeriodAmount
                value: absent
              - type: value
                key: budgetFilter.services
                op: contains
                value: services/C7E2-9256-1C43

    """

    class resource_type(ChildTypeInfo):
        service = 'billingbudgets'
        version = 'v1'
        component = 'billingAccounts.budgets'
        enum_spec = ('list', 'budgets[]', None)
        scope = None
        name = id = 'name'
        default_report_fields = ['name', 'displayName']
        parent_spec = {
            'resource': 'cloudbilling-account',
            'child_enum_params': [
                ('name', 'parent'),
            ],
            'parent_get_params': [
                ('name', 'name', 'regex', r'(billingAccounts/[^/]+)/'),
            ],
        }
        asset_type = "billingbudgets.googleapis.com/Budget"
        permissions = ('billing.budgets.list', 'billing.accounts.list')
        urn_component = "budget"
        urn_id_segments = (-1,)


@BillingBudget.action_registry.register('update')
class BillingBudgetUpdate(MethodAction):
    """Update a billing budget's amount, threshold rules, or notifications.

    Calls ``billingAccounts.budgets.patch`` with an ``updateMask`` naming
    only the fields this action changes. Budgets that already match the
    requested settings are skipped.

    - ``use-last-period-amount``: replaces the budget amount with
      ``lastPeriodAmount`` so the limit tracks the previous period's
      actual spend. The API only allows this for budgets on a calendar
      period, so budgets with a ``customPeriod`` are skipped.
    - ``add-threshold``: appends a threshold rule at this fraction of the
      budget (``0.25`` is 25%) unless one already exists at that value.
      Existing threshold rules are kept.
    - ``pubsub-topic``: sets ``notificationsRule.pubsubTopic`` (in the form
      ``projects/{project_id}/topics/{topic_id}``) and the required
      ``schemaVersion`` of ``1.0``. The caller needs
      ``pubsub.topics.setIamPolicy`` on the topic.

    :example:

    .. code-block:: yaml

        policies:
          - name: gcp-billing-budget-use-baseline
            resource: gcp.billing-budget
            filters:
              - type: value
                key: amount.lastPeriodAmount
                value: absent
            actions:
              - type: update
                use-last-period-amount: true
                add-threshold: 0.25
                pubsub-topic: projects/my-project/topics/budget-alerts
    """

    schema = type_schema(
        'update',
        **{
            'use-last-period-amount': {'type': 'boolean'},
            'add-threshold': {'type': 'number', 'minimum': 0},
            'pubsub-topic': {
                'type': 'string',
                'pattern': '^projects/[^/]+/topics/[^/]+$',
            },
        }
    )
    method_spec = {'op': 'patch'}
    permissions = ('billing.budgets.update',)

    def validate(self):
        super().validate()
        if not (self.data.keys() - {'type'}):
            raise PolicyValidationError(
                f"policy:{self.manager.ctx.policy.name} action:{self.type} "
                "requires at least one of: use-last-period-amount, "
                "add-threshold, pubsub-topic")
        return self

    def process_resource_set(self, client, model, resources):
        for resource in resources:
            params = self.get_resource_params(model, resource)
            if params is None:
                continue
            self.invoke_api(client, self.method_spec['op'], params)

    def get_resource_params(self, model, resource):
        body = {}
        mask = []

        if self.data.get('use-last-period-amount'):
            if 'customPeriod' in resource.get('budgetFilter', {}):
                self.log.warning(
                    f"policy:{self.manager.ctx.policy.name} action:{self.type} "
                    f"skipping use-last-period-amount for {resource['name']}: "
                    "lastPeriodAmount cannot be combined with customPeriod")
            elif 'lastPeriodAmount' not in resource.get('amount', {}):
                body['amount'] = {'lastPeriodAmount': {}}
                mask.append('amount')

        threshold = self.data.get('add-threshold')
        if threshold is not None:
            rules = list(resource.get('thresholdRules', []))
            if not any(r.get('thresholdPercent') == threshold for r in rules):
                rules.append({'thresholdPercent': threshold})
                body['thresholdRules'] = rules
                mask.append('thresholdRules')

        topic = self.data.get('pubsub-topic')
        if topic:
            rule = resource.get('notificationsRule', {})
            if rule.get('pubsubTopic') != topic or rule.get('schemaVersion') != '1.0':
                body['notificationsRule'] = {
                    'pubsubTopic': topic,
                    'schemaVersion': '1.0',
                }
                mask.extend([
                    'notificationsRule.pubsubTopic',
                    'notificationsRule.schemaVersion',
                ])

        if not mask:
            return None
        if resource.get('etag'):
            body['etag'] = resource['etag']
        return {
            'name': resource['name'],
            'updateMask': ','.join(mask),
            'body': body,
        }
