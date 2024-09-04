# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query
from c7n.utils import merge_dict_list


class DescribeInspector2Finding(query.DescribeSource):
    def resources(self, query):
        """Only show active Inspector V2 findings by default

        Unless overridden by policy, use this default filter:

        - FindingStatus: ACTIVE
        """
        query = merge_dict_list(
            [
                {
                    "filterCriteria": {
                        "findingStatus": [
                            {
                                "comparison": "EQUALS",
                                "value": "ACTIVE"
                            }
                        ]
                    }
                },
                *self.manager.data.get("query", []),
                query,
            ]
        )
        return super().resources(query=query)


@resources.register("inspector2-finding")
class Inspector2Finding(query.QueryResourceManager):
    """AWS Inspector V2 Findings

    :example:

    Use the default filter set, which includes active findings

    .. code-block:: yaml

        policies:
          - name: aws-inspector2-finding
            resource: aws.inspector2-finding

    :example:

    Show High and Medium severity findings for a specific finding type
    It will override default filters that show all Active findings

    .. code-block:: yaml

        policies:
          - name: aws-inspector2-finding
            resource: aws.inspector2-finding
            query:
              - filterCriteria:
                  findingType:
                    - comparison: EQUALS
                      value: PACKAGE_VULNERABILITY
                  severity:
                    - comparison: EQUALS
                      value: HIGH
                    - comparison: EQUALS
                      value: MEDIUM



    Reference for available filters:

    https://docs.aws.amazon.com/inspector/v2/APIReference/API_FilterCriteria.html#inspector2-Type-FilterCriteria-findingType
    """  # noqa: E501

    class resource_type(query.TypeInfo):
        service = "inspector2"
        enum_spec = ('list_findings', 'findings', None)
        arn = 'findingArn'
        arn_type = 'finding'
        id = "findingArn"
        name = "title"

    source_mapping = {
        "describe": DescribeInspector2Finding,
    }
