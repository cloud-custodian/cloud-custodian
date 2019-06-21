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
from __future__ import absolute_import

import itertools
import logging
import operator
import os

import click
import yaml

from docutils import nodes
from docutils.statemachine import ViewList
from docutils.parsers.rst.directives import unchanged

from jinja2 import Environment, PackageLoader

from sphinx.directives import SphinxDirective as Directive
from sphinx.util.nodes import nested_parse_with_titles

from c7n.schema import (
    ElementSchema, resource_vocabulary, generate as generate_schema)
from c7n.resources import load_resources
from c7n.provider import clouds

log = logging.getLogger('c7nsphinx')


def template_underline(value, under="="):
    return len(value) * under


def get_environment():
    env = Environment(loader=PackageLoader('c7n_sphinxext', '_templates'))
    env.globals['underline'] = template_underline
    env.globals['ename'] = ElementSchema.name
    env.globals['edoc'] = ElementSchema.doc
    env.globals['eschema'] = CustodianSchema.render_schema
    env.globals['render_resource'] = CustodianResource.render_resource
    return env


class CustodianDirective(Directive):

    has_content = True
    required_arguments = 1

    vocabulary = None
    env = None

    def _parse(self, rst_text, annotation):
        result = ViewList()
        for line in rst_text.split("\n"):
            result.append(line, annotation)
        node = nodes.paragraph()
        node.document = self.state.document
        nested_parse_with_titles(self.state, result, node)
        return node.children

    def _nodify(self, template_name, annotation, variables):
        return self._parse(
            self._render(template_name, variables), annotation)

    @classmethod
    def _render(cls, template_name, variables):
        t = cls.env.get_template(template_name)
        return t.render(**variables)

    @classmethod
    def resolve(cls, schema_path):
        return ElementSchema.resolve(cls.vocabulary, schema_path)


class CustodianResource(CustodianDirective):

    @classmethod
    def render_resource(cls, resource_path):
        resource_class = cls.resolve(resource_path)
        provider_name, resource_name = resource_path.split('.', 1)
        return cls._render('resource.rst',
            variables=dict(
                provider_name=provider_name,
                resource_name="%s.%s" % (provider_name, resource_class.type),
                filters=ElementSchema.elements(resource_class.filter_registry),
                actions=ElementSchema.elements(resource_class.action_registry),
                resource=resource_class))


class CustodianSchema(CustodianDirective):

    option_spec = {'module': unchanged}

    @classmethod
    def render_schema(cls, el):
        return cls._render(
            'schema.rst',
            {'schema_yaml': yaml.safe_dump(
                ElementSchema.schema(cls.definitions, el),
                default_flow_style=False)})

    def run(self):
        schema_path = self.arguments[0]
        el = self.resolve(schema_path)
        schema_yaml = yaml.safe_dump(
            ElementSchema.schema(self.definitions, el), default_flow_style=False)
        return self._nodify(
            'schema.rst', '<c7n-schema>',
            dict(name=schema_path, schema_yaml=schema_yaml))


INITIALIZED = False


def init():
    global INITIALIZED
    if INITIALIZED:
        return
    load_resources()
    CustodianDirective.vocabulary = resource_vocabulary()
    CustodianDirective.definitions = generate_schema()['definitions']
    CustodianDirective.env = env = get_environment()
    INITIALIZED = True
    return env


def setup(app):
    init()

    app.add_directive_to_domain(
        'py', 'c7n-schema', CustodianSchema)

    app.add_directive_to_domain(
        'py', 'c7n-resource', CustodianResource)

    return {'version': '0.1',
            'parallel_read_safe': True,
            'parallel_write_safe': True}


@click.command()
@click.option('--provider', required=True)
@click.option('--output-dir', type=click.Path(), required=True)
@click.option('--group-by')
def main(provider, output_dir, group_by):
    try:
        _main(provider, output_dir, group_by)
    except Exception:
        import traceback, pdb, sys
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])


def _main(provider, output_dir, group_by):
    """Generate RST docs for a given cloud provider's resources
    """
    env = init()

    logging.basicConfig(level=logging.INFO)
    output_dir = os.path.abspath(output_dir)
    provider_class = clouds[provider]

    # group by will be provider specific, supports nested attributes
    group_by = operator.attrgetter(group_by or "type")

    files = []

    # Write out resources by grouped page
    for key, group in itertools.groupby(
            sorted(provider_class.resources.values(), key=group_by), key=group_by):
        rpath = os.path.join(output_dir, "%s.rst" % key)
        with open(rpath, 'w') as fh:
            t = env.get_template('provider-resource.rst')
            fh.write(t.render(
                provider_name=provider,
                key=key,
                resources=sorted(group, key=operator.attrgetter('type'))))
        files.append(os.path.basename(rpath))

    # Write out common provider filters & actions
    common_actions = {}
    common_filters = {}
    for r in provider_class.resources.values():
        for f in ElementSchema.elements(r.filter_registry):
            if not f.schema_alias:
                continue
            common_filters[ElementSchema.name(f)] = (f, r)

        for a in ElementSchema.elements(r.action_registry):
            if not a.schema_alias:
                continue
            common_actions[ElementSchema.name(a)] = (a, r)

    fpath = os.path.join(
        output_dir, "%s-common-filters.rst" % provider_class.type.lower())
    with open(fpath, 'w') as fh:
        t = env.get_template('provider-common-elements.rst')
        fh.write(t.render(
            provider_name=provider_class.display_name,
            element_type='filters',
            elements=[common_filters[k] for k in sorted(common_filters)]))
        files.insert(0, os.path.basename(fpath))

    fpath = os.path.join(
        output_dir, "%s-common-actions.rst" % provider_class.type.lower())
    with open(fpath, 'w') as fh:
        t = env.get_template('provider-common-elements.rst')
        fh.write(t.render(
            provider_name=provider_class.display_name,
            element_type='actions',
            elements=[common_actions[k] for k in sorted(common_actions)]))
        files.insert(0, os.path.basename(fpath))

    log.info("%s Wrote %d resources groups", provider.title(), len(files))

    # Write out the provider index
    provider_path = os.path.join(output_dir, 'index.rst')
    with open(provider_path, 'w') as fh:
        log.info("Writing Provider Index to %s", provider_path)
        t = env.get_template('provider-index.rst')
        fh.write(t.render(provider_name=provider_class.display_name, files=files))
