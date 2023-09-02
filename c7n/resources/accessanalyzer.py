# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query
from c7n.utils import local_session
from c7n.exceptions import PolicyExecutionError



class DescribeAccessanalyzerFinding(query.DescribeSource):

    def resources(self, query):
        analyzer_arn = self.get_analyzer_arn()
        if not analyzer_arn:
            return ()
        if not query:
            query = {}
        query['analyzerArn'] = analyzer_arn
        return super().resources(query)

    def get_analyzer_arn(self):
        """ Find Active Access Analyzer ARN
        """
        client = local_session(self.manager.session_factory).client('accessanalyzer')
        analyzers = client.list_analyzers(type='ACCOUNT').get('analyzers', ())
        found = False
        for analyzer in analyzers:
            if analyzer['status'] != 'ACTIVE':
                continue
            # If this account is the Management/delegated administrator for IAM Access Analyzer, organization analyzer is prefered
            if analyzer['type'] == 'ORGANIZATION':
                found = analyzer
                break
            found = analyzer
        if not found:
            raise PolicyExecutionError(
                f"policy:{self.manager.ctx.policy.name} no active access analyzer found in account"
                )
        return found['arn']


@resources.register("iam-access-analyzer-finding")
class AccessanalyzerFinding(query.QueryResourceManager):
    """AWS IAM Access Analyzer Findings resource
    """
    class resource_type(query.TypeInfo):
        service = "accessanalyzer"
        enum_spec = ('list_findings', 'findings', None)
        id = "id"
        name = "resourceType"

    source_mapping = {
        "describe": DescribeAccessanalyzerFinding,
    }
