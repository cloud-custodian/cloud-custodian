from c7n.manager import resources
from c7n.query import (
    QueryResourceManager,
    TypeInfo,
    DescribeSource,
    ConfigSource,
)
from c7n.tags import universal_augment


class DescribeVoiceConnector(DescribeSource):
    # override default describe augment to get tags
    def augment(self, resources):
        tagged_resources = universal_augment(self.manager, resources)
        return tagged_resources


@resources.register('chime-voice-voiceconnector')
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

        # cfn_type = None
        # config_type = None
        permission_prefix = 'chime'

        universal_taggable = object()
