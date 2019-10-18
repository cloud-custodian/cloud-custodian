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
import importlib_metadata as pkgmd
import jinja2


def package_deps(package, deps):
    pdeps = pkgmd.requires(package) or ()
    for r in pdeps:
        # skip optional deps
        if ';' in r:
            continue
        for idx, c in enumerate(r):
            if not c.isalnum() and c not in ('-', '_', '.'):
                break
        if idx + 1 == len(r):
            idx += 1
        pkg_name = r[:idx]
        if pkg_name not in deps:
            deps.append(pkg_name)
            package_deps(pkg_name, deps)
    return deps


@click.command()
@click.option('--package', required=True)
@click.option('--template', type=click.Path())
@click.option('--output', type=click.Path())
def main(package, template, output):
    """recursive dependency pinning for package"""
    pinned_dep_graph = []
    deps = []
    package_deps(package, deps)

    for d in sorted(deps):
        pinned_dep_graph.append(
            '%s==%s' % (d, pkgmd.distribution(d).version))

    if not template and output:
        print('\n'.join(pinned_dep_graph))
        return

    with open(template) as fh:
        t = jinja2.Template(fh.read(), trim_blocks=True, lstrip_blocks=True)
    with open(output, 'w') as fh:
        fh.write(t.render(pinned_packages=pinned_dep_graph))


if __name__ == '__main__':
    main()
