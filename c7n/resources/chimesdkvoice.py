from c7n.manager import resources
from c7n.query import (
    ChildResourceManager,
    QueryResourceManager,
    TypeInfo,
    DescribeSource,
    ChildDescribeSource,
    ConfigSource,
)
from c7n.resources.aws import Arn
from c7n.tags import universal_augment
from c7n.utils import local_session


class DescribeVoiceConnector(DescribeSource):
    # override default describe augment to get tags
    def augment(self, resources):
        tagged_resources = universal_augment(self.manager, resources)
        return tagged_resources



@resources.register('chimesdkvoice-voiceconnector')
class VoiceConnector(QueryResourceManager):
    source_mapping = {'describe': DescribeVoiceConnector,
                      'config': ConfigSource}
    # interior class that defines the aws metadata for resource
    class resource_type(TypeInfo):
        service = 'chime-sdk-voice'

        enum_spec = ['list_voice_connectors', 'VoiceConnectors', None]

        id = 'VoiceConnectorId'
        name = 'Name'
        arn = 'VoiceConnectorArn'
        date = 'CreatedTimestamp'

        cfn_type = None
        config_type = None

        universal_taggable = object()
