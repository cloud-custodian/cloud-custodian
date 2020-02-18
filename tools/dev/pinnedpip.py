# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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
from c7n.mu import generate_requirements
import jinja2


@click.command()
@click.option('--package', required=True)
@click.option('--template', type=click.Path())
@click.option('--output', type=click.Path())
def main(package, template, output):
    """recursive dependency pinning for package"""
    requirements = generate_requirements(package)
    pinned_packages = requirements.split('\n')
    if not template and output:
        print('\n'.join(pinned_packages))
        return

    with open(template) as fh:
        t = jinja2.Template(fh.read(), trim_blocks=True, lstrip_blocks=True)
    with open(output, 'w') as fh:
        fh.write(t.render(pinned_packages=pinned_packages))


if __name__ == '__main__':
    main()
