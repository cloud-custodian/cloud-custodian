# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import DescribeSource, QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema
from c7n.tags import universal_augment

class DescribeConfigurationSet(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('ses')
        for r in resources:
            details = client.describe_configuration_set(ConfigurationSetName=r['Name'], 
                ConfigurationSetAttributeNames=['eventDestinations','trackingOptions','deliveryOptions','reputationOptions'])
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
