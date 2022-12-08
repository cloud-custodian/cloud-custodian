# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
