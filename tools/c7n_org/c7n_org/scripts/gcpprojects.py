# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import click
import yaml

from c7n_gcp.client import Session


@click.command()
@click.option(
    '-f', '--output', type=click.File('w'), default='-',
    help="File to store the generated config (default stdout)")
def main(output):
    """
    Generate a c7n-org gcp projects config file
    """

    client = Session().client('cloudresourcemanager', 'v1', 'projects')

    results = []
    for page in client.execute_paged_query('list', {}):
        for project in page.get('projects', []):

            if project['lifecycleState'] != 'ACTIVE':
                continue

            project_info = {
                'project_id': project['projectId'],
                'name': project.get('name', project['projectId']),
            }

            if 'labels' in project:
                project_info['tags'] = [
                    'label:%s:%s' % (k, v) for k, v in project.get('labels', {}).items()]
            results.append(project_info)

    output.write(
        yaml.safe_dump({'projects': results}, default_flow_style=False))


if __name__ == '__main__':
    main()
