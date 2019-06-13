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

from sphinx.errors import SphinxError
from sphinx.directives import SphinxDirective as Directive
from sphinx.util.nodes import nested_parse_with_titles

from c7n.schema import resource_vocabulary
from c7n.resources import load_resources
from c7n.provider import clouds


log = logging.getLogger('c7nsphinx')


def template_underline(value, under="="):
    return len(value) * under


def get_environment():
    env = Environment(loader=PackageLoader('c7n_sphinxext', '_templates'))
    env.globals['underline'] = template_underline
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
        current = cls.vocabulary
        frag = None
        if schema_path.startswith('.'):
            # The preprended '.' is an odd artifact
            schema_path = schema_path[1:]
        parts = schema_path.split('.')
        while parts:
            k = parts.pop(0)
            if frag:
                k = "%s.%s" % (frag, k)
                frag = None
                parts.insert(0, 'classes')
            elif k in clouds:
                frag = k
                if len(parts) == 1:
                    parts.append('resource')
                continue
            if k not in current:
                raise ValueError("Invalid schema path %s" % schema_path)
            current = current[k]
        return current


class CustodianResource(CustodianDirective):

    @classmethod
    def render_resource(cls, resource_path):
        resource_class = cls.resolve(resource_path)
        provider_name, resource_name = resource_path.split('.', 1)
        return cls._render('resource.rst',
            variables=dict(
                resource_name="%s.%s" % (provider_name, resource_class.type),
                filters=sorted(
                    [f for f in resource_class.filter_registry.values()
                     if f.type not in {'or', 'and', 'not'}],
                    key=operator.attrgetter('type')),
                actions=sorted(
                    resource_class.action_registry.values(),
                    key=operator.attrgetter('type')),
                resource=resource_class))

    def run(self):
        return self._nodify(
            'resource.rst', '<c7n-resource>', self.render_resource(self.arguments[0]))


class CustodianSchema(CustodianDirective):

    option_spec = {'module': unchanged}

    def run(self):
        schema_path = self.arguments[0]
        schema = self.resolve(schema_path).schema

        if schema is None:
            raise SphinxError(
                "Unable to generate reference docs for %s, no schema found" % (
                    schema_path))

        schema_json = yaml.safe_dump(schema, default_flow_style=False)
        return self._nodify(
            'schema.rst', '<c7n-schema>',
            dict(name=schema_path, schema_json=schema_json))


INITIALIZED = False


def init():
    global INITIALIZED
    if INITIALIZED:
        return
    load_resources()
    CustodianDirective.vocabulary = resource_vocabulary()
    CustodianDirective.env = env = get_environment()
    INITIALIZED = True
    return env


def setup(app):
    init()

    app.add_directive_to_domain(
        'py', 'c7n-schema', CustodianSchema)

    app.add_directive_to_domain(
        'py', 'c7n-resource', CustodianResource)


@click.command()
@click.option('--provider', required=True)
@click.option('--output-dir', type=click.Path(), required=True)
@click.option('--group-by')
def main(provider, output_dir, group_by):
    """Generate RST docs for a given cloud provider's resources
    """
    env = init()

    logging.basicConfig(level=logging.INFO)
    output_dir = os.path.abspath(output_dir)
    provider_class = clouds[provider]

    # group by will be provider specific, supports nested attributes
    group_by = operator.attrgetter(group_by or "type")

    for key, group in itertools.groupby(
            sorted(provider_class.resources.values(), key=group_by), key=group_by):
        rpath = os.path.join(output_dir, "%s.rst" % key)
        with open(rpath, 'w') as fh:
            log.info("Writing ResourceGroup:%s.%s to %s", provider, key, rpath)
            t = env.get_template('provider-resource.rst')
            fh.write(t.render(
                provider_name=provider,
                key=key,
                resources=sorted(group, key=operator.attrgetter('type'))))

    provider_path = os.path.join(output_dir, 'index.rst')
    with open(provider_path, 'w') as fh:
        log.info("Writing Provider Index to %s", provider_path)
        t = env.get_template('provider-index.rst')
        fh.write(t.render(provider_name=provider))
