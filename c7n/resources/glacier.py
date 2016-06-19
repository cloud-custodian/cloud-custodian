from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('glacier')
class Glacier(QueryResourceManager):

    class Meta(object):
        services = 'glacier'
        enum_spec = ('list_vaults', 'VaultList', None)
        name = "VaultName"
        id = "VaultARN"
