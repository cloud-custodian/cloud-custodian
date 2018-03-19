from c7n.manager import ResourceManager
from c7n.query import sources
from c7n.utils import local_session


class ResourceQuery(object):

    def __init__(self, session_factory):
        self.session_factory = session_factory

    def filter(self, resource_manager, **params):
        m = resource_manager.resource_type
        client = local_session(self.session_factory).client(
            "%s.%s" % (m.service, m.client))

        


    
class QueryResourceManager(object):
    pass
