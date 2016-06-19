from botocore.exceptions import ClientError

from c7n.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.utils import local_session
from c7n.query import QueryResourceManager


@resources.register('sqs')
class SQS(QueryResourceManager):

    resource_type = 'aws.sqs.queue'

    def augment(self, resources):

        def _augment(r):
            client = local_session(self.session_factory).client('sqs')
            try:
                queue = client.get_queue_attributes(
                    QueueUrl=r,
                    AttributeNames=['All'])['Attributes']
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDenied':
                    self.log.warning("Denied access to sqs %s" % r)
                    return
                raise

            queue['QueueUrl'] = r
            return queue

        self.log.debug('retrieving details for %d queues' % len(resources))
        with self.executor_factory(max_workers=4) as w:
            return filter(None, w.map(_augment, resources))


SQS.filter_registry.register('cross-account', CrossAccountAccessFilter)
