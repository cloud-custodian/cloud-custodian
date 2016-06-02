

from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('iam-group')
class Group(QueryResourceManager):

    resource_type = 'aws.iam.Group'


@resources.register('iam-role')
class Role(QueryResourceManager):

    resource_type = 'aws.iam.Role'


@resources.register('iam-user')
class User(QueryResourceManager):

    resource_type = 'aws.iam.User'


@resources.register('iam-policy')
class Policy(QueryResourceManager):

    resource_type = 'aws.iam.Policy'


@resources.register('iam-profile')
class InstanceProfile(QueryResourceManager):

    resource_type = 'aws.iam.instance-profile'


@resources.register('server-cert')
class ServerCerficate(QueryResourceManager):

    resource_type = 'aws.iam.server-certficate'


