from c7n.provider import resources, local_session
from c7n.query import QueryResourceManager

METRICS = ['JobRunTime', 'WorkersUsed']

@resources.register('emr-serverless-jobs')
class EMRServerlessJobs(QueryResourceManager):

    class resource_type:
        service = 'emr'
        enum_spec = ('list_jobs', 'Jobs', None)
        detail_spec = ('describe_job', 'JobId', 'JobId', 'Job')
        id = 'Id'
        name = 'Name'
        date = 'CreatedOn'
        dimension = None


    def get_metrics(self):
        client = local_session(self.session_factory).client('emr')
        for job in self.resources():
            response = client.list_metrics(
                JobId=job['Id'],
                Metrics=METRICS
            )
            job['Metrics'] = response['Metrics']

