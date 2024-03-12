# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.config import Bag
from c7n.manager import resources
from c7n.utils import local_session, type_schema, filter_empty
from .core import Filter, ListItemResourceManager


class RecommendationManager(ListItemResourceManager):

    model = Bag(id='recommendationId')

    @classmethod
    def get_model(cls):
        return cls.model


class CostHubRecommendation(Filter):
    """Cost optimization hub recommendations.

    .. code-block:: yaml

      - name: cost-ec2-optimize
        resource: aws.ec2
        filters:
          - type: cost-optimization
            attrs:
             - actionType: Rightsize
             - key: recommendationLookbackPeriodInDays
               op: gte
               value: 10
             - key: estimatedMonthlySavings
               value: 30
               op: gte

    """

    schema = type_schema(
        'cost-optimization',
        efforts={
            'type': 'array',
            'items': {'enum': ['VeryLow', 'Low', 'Medium', 'High', 'VeryHigh']},
        },
        action={
            'enum': [
                'Rightsize',
                'Stop',
                'Upgrade',
                'PurchaseSavingsPlans',
                'PurchaseReservedInstances',
                'MigrateToGraviton',
            ]
        },
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
    )
    schema_alias = True
    resource_type_map = {
        'ec2': 'Ec2Instance',
        'ebs': 'EbsVolume',
        'lambda': 'LambdaFunction',
        'ecs-service': 'EcsService',
        'asg': 'Ec2AutoScalingGroup',
    }
    default_action = {
        'ec2': 'Rightsize',
        'ebs': 'Upgrade',
        'ecs-service': 'Rightsize',
        'lambda': 'Rightsize',
    }

    permissions = ('cost-optimization-hub:ListRecommendations',)
    annotation_key = "c7n:cost_optimize"

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client(
            'cost-optimization-hub', region_name='us-east-1')
        filter_params = filter_empty({
            'actionTypes': [
                self.manager.data.get(
                    'action', self.default_action[self.manager.type]
                )
            ],
            'regions': [self.manager.config.region] or None,
            'resourceTypes': [self.resource_type_map[self.manager.type]],
        })
        r_map = {}
        for arn, r in zip(self.manager.get_arns(resources), resources):
            r_map[arn] = r

        pager = client.get_paginator('list_recommendations')
        recommendations = pager.paginate(filter=filter_params).build_full_result()

        results = set()
        frm = RecommendationManager(self.manager.ctx, data={'filters': self.data.get('attrs', [])})

        for rec in recommendations['items']:
            rec_rarn = rec['resourceArn']

            # a few of the recommendation resources use a version
            # qualifier which won't match the innate/latest arn coming
            # from describe sources (sans qualifier)
            if rec_rarn.count(':') == 7:
                rec_rarn, _ = rec_rarn.rsplit(':', 1)

            if rec_rarn not in r_map:
                continue
            if not frm.filter_resources([rec], event):
                continue
            r = r_map[rec_rarn]
            r[self.annotation_key] = rec
            results.add(rec_rarn)
        return [r for rid, r in r_map.items() if rid in results]

    @classmethod
    def register_resources(klass, registry, resource_class):
        if resource_class.type in klass.resource_type_map:
            resource_class.filter_registry.register('cost-optimization', klass)


resources.subscribe(CostHubRecommendation.register_resources)
