from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import local_session


@resources.register('sqs')
class SQS(QueryResourceManager):

    resource_type = 'aws.sqs.queue'

    def augment(self, resources):

        def _augment(r):
            client = local_session(self.session_factory).client('sqs')
            queue = client.get_queue_attributes(
                QueueUrl=r,
                AttributeNames=['All'])['Attributes']
            queue['QueueUrl'] = r
            return queue

        self.log.debug('retrieving details for %d queues' % len(resources))
        with self.executor_factory(max_workers=4) as w:
            return list(w.map(_augment, resources))

