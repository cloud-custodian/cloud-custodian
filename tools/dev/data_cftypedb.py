# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

import boto3
import click
import jmespath

from botocore.paginate import Paginator


@click.command()
@click.option('-f', '--output', default='-', type=click.File('w'))
def main(output):

    client = boto3.client('cloudformation')

    paginator = Paginator(
        client.list_types,
        {'input_token': 'NextToken',
         'output_token': 'NextToken',
         'result_key': 'TypeSummaries'},
        client.meta.service_model.operation_model('ListTypes'))

    results = paginator.paginate(Visibility='PUBLIC').build_full_result()
    type_names = jmespath.search('TypeSummaries[].TypeName', results)

    # filter out non aws ones
    type_names = [t for t in type_names if t.startswith('AWS:')]

    # manually add the ones missing
    missing = (
        'AWS::::Account',
        'AWS::Serverless::Application',)
    for m in missing:
        if m not in type_names:
            type_names.append(m)

    output.write(json.dumps(sorted(type_names), indent=2))


if __name__ == '__main__':
    main()
