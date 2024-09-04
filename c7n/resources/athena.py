# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


@resources.register("athena-named-query")
class AthenaNamedQuery(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = "athena"
        enum_spec = ('list_named_queries', 'NamedQueryIds', None)
        batch_detail_spec = ('batch_get_named_query', 'NamedQueryIds', None, 'NamedQueries', None)
        arn = False
        id = "NamedQueryId"
        name = "Name"
        cfn_type = "AWS::Athena::NamedQuery"
        permissions_augment = ("athena:ListTagsForResource",)
