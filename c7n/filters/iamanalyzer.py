# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from .core import ValueFilter

from c7n.exceptions import PolicyExecutionError
from c7n.manager import resources
from c7n.utils import type_schema, local_session, chunks


class AccessAnalyzer(ValueFilter):
    """Analyze resource access policies using AWS IAM Access Analyzer.

    Access analyzer uses logic based reasoning to analyze embedded resource
    iam access policies to determine access outside of a zone of trust.

    .. code-block:: yaml

       policies:
         - name: s3-check
           resource: aws.s3
           filters:
             - type: iam-analyzer
               key: isPublic
               value: true

    """

    schema = type_schema('iam-analyzer',
        analyzer={'type': 'string'}, rinherit=ValueFilter.schema)
    schema_alias = True
    permissions = ('access-analyzer:ListFindings', 'access-analyzer:ListAnalyzers')
    supported_types = (
        'AWS::IAM::Role',
        'AWS::KMS::Key',
        'AWS::Lambda::Function',
        'AWS::Lambda::LayerVersion',
        'AWS::S3::Bucket',
        'AWS::SQS::Queue',
    )

    analysis_annotation = 'c7n:AccessAnalysis'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('accessanalyzer')
        analyzer_arn = self.get_analyzer(client)
        results = []
        self.annotate = False
        self.get_findings(
            client, analyzer_arn,
            [r for r in resources if self.analysis_annotation not in r])
        for r in resources:
            findings = r.get(self.analysis_annotation, [])
            if not findings:
                continue
            elif not len(self.data) > 1:
                results.append(r)
                continue
            found = False
            for f in findings:
                if self(f):
                    found = True
                    break
            if found:
                results.append(r)
        return results

    def get_findings(self, client, analyzer_arn, resources):
        for resource_set in chunks(
                zip(self.manager.get_arns(resources), resources),
                20):
            resource_set = dict(resource_set)
            filters = {
                'status': {'eq': ['ACTIVE']},
                'resource': {'contains': list(resource_set)},
                'resourceType': {'eq': [self.manager.resource_type.cfn_type]}
            }
            for finding in self.manager.retry(
                    client.list_findings,
                    analyzerArn=analyzer_arn, filter=filters).get('findings', ()):
                r = resource_set[finding['resource']]
                r.setdefault(self.analysis_annotation, []).append(finding)

    def get_analyzer(self, client):
        if self.data.get('analyzer'):
            return self.data['analyzer']
        analyzers = client.list_analyzers(type='ACCOUNT').get('analyzers', ())
        found = False
        for a in analyzers:
            if a['status'] != 'ACTIVE':
                continue
            found = a
        if not found:
            raise PolicyExecutionError(
                "policy:%s no access analyzer found in account or org analyzer specified" % (
                    self.manager.ctx.policy.name
                ))
        return found['arn']

    @classmethod
    def register_resources(klass, registry, resource_class):
        if resource_class.resource_type.cfn_type not in klass.supported_types:
            return
        resource_class.filter_registry.register('iam-analyzer', klass)


resources.subscribe(AccessAnalyzer.register_resources)
