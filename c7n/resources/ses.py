# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import DescribeSource, QueryResourceManager, TypeInfo
from c7n.utils import local_session
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

