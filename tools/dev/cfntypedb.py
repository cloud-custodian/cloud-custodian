# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import boto3
import json
import jmespath

from botocore.paginate import Paginator


def main():

    client = boto3.client('cloudformation')

    paginator = Paginator(
        client.list_types,
        {'input_token': 'NextToken',
         'output_token': 'NextToken',
         'result_key': 'TypeSummaries'},
        client.meta.service_model.operation_model('ListTypes'))

    results = paginator.paginate(Visibility='PUBLIC').build_full_result()
    type_names = jmespath.search('TypeSummaries[].TypeName', results)

    # manually add the ones missing
    missing = (
        'AWS::Serverless::Application',)
    for m in missing:
        if m not in type_names:
            type_names.append(m)
    print(json.dumps(sorted(type_names), indent=2))


if __name__ == '__main__':
    main()
