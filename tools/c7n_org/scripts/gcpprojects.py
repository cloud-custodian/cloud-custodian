# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
                'name': project['name'],
            }

            if 'labels' in project:
                project_info['tags'] = [
                    'label:%s:%s' % (k, v) for k, v in project.get('labels', {}).items()]
            results.append(project_info)

    output.write(
        yaml.safe_dump({'projects': results}, default_flow_style=False))


if __name__ == '__main__':
    main()
