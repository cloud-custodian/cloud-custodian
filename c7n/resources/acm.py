
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session


@resources.register('acm-certificate')
class Certificate(QueryResourceManager):

    class Meta(object):
        service = 'acm'
        enum_spec = ('list_certificates', 'CertificateSummaryList', None)
        id = 'CertificateArn'
        name = 'DomainName'
        date = 'CreatedAt'

    resource_type = Meta

    def augment(self, resources):

        def _augment(r):
            client = local_session(self.session_factory).client('acm')
            attrs = client.describe_certificate(CertificateArn=r)['Certificate']
            r.update(attrs)
            return r

        with self.executor_factory(max_workers=3) as w:
            return list(w.map(_augment, resources))
                
            
