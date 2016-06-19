

from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import local_session


@resources.register('sns')
class SNS(QueryResourceManager):

    resource_type = 'aws.sns.topic'

    def augment(self, resources):

        def _augment(r):
            client = local_session(self.session_factory).client('sns')
            attrs = client.get_topic_attributes(
                TopicArn=r['TopicArn'])['Attributes']
            r.update(attrs)
            return r

        with self.executor_factory(max_workers=4) as w:
            return list(w.map(_augment, resources))
