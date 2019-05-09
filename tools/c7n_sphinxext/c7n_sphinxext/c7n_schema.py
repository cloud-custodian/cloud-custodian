"""
Based on bokeh_model.py Sphinx Extension from Bokeh project:
https://github.com/bokeh/bokeh/tree/master/bokeh/sphinxext
"""

from __future__ import absolute_import

import importlib
import json
import re

from docutils import nodes
from docutils.statemachine import ViewList
from docutils.parsers.rst.directives import unchanged

from sphinx.errors import SphinxError
from sphinx.directives import SphinxDirective as Directive
from sphinx.util.nodes import nested_parse_with_titles

from .templates import get_template

from c7n.utils import reformat_schema
from c7n.resources import load_resources
from c7n.provider import clouds


# taken from Sphinx autodoc
py_sig_re = re.compile(
    r'''^ ([\w.]*\.)?            # class name(s)
          (\w+)  \s*             # thing name
          (?: \((.*)\)           # optional: arguments
           (?:\s* -> \s* (.*))?  #           return annotation
          )? $                   # and nothing more
          ''', re.VERBOSE)


class CustodianDirective(Directive):

    has_content = True

    def _parse(self, rst_text, annotation):
        result = ViewList()
        for line in rst_text.split("\n"):
            result.append(line, annotation)
        node = nodes.paragraph()
        node.document = self.state.document
        nested_parse_with_titles(self.state, result, node)
        return node.children

    def _nodify(self, template_name, annotation, variables):
        t = get_template(template_name)
        return self._parse(t.render(**variables), annotation)


class CustodianResource(CustodianDirective):

    required_arguments = 1

    def run(self):

        resource = self.arguments[0]
        if '.' in resource:
            provider_name, resource_name = resource.split('.', 1)
        else:
            provider_name, resource_name = 'aws', resource

        provider = clouds.get(provider_name)
        resource_class = provider.resources.get(resource_name)

        return self._nodify(
            'c7n_resource.rst', '<c7n-resource>',
            resource_name="%s.%s" % (provider.type, resource_class.type),
            resource=resource_class)


class CustodianSchema(CustodianDirective):

    required_arguments = 1
    optional_arguments = 2

    option_spec = {
        'module': unchanged
    }

    def run(self):
        sig = " ".join(self.arguments)

        m = py_sig_re.match(sig)
        if m is None:
            raise SphinxError("Unable to parse signature for c7n-schema: %r" % sig)
        name_prefix, model_name, arglist, ret_ann = m.groups()

        module_name = self.options['module']

        try:
            module = importlib.import_module(module_name)
        except ImportError:
            raise SphinxError(
                "Unable to generate reference docs for %s, couldn't import module '%s'" %
                (model_name, module_name))

        model = getattr(module, model_name, None)
        if model is None:
            raise SphinxError(
                "Unable to generate reference docs for %s, no model '%s' in %s" %
                (model_name, model_name, module_name))

        if not hasattr(model, 'schema'):
            raise SphinxError(
                "Unable to generate reference docs for %s, model '%s' does not\
                 have a 'schema' attribute" % (model_name, model_name))

        schema = reformat_schema(model)
        schema_json = json.dumps(
            schema, sort_keys=True,
            indent=2, separators=(',', ': '))
        return self._nodify(
            'c7n_schema.rst', '<c7n-schema>',
            dict(name=model_name,
                 module_name=module_name,
                 schema_json=schema_json))


def setup(app):

    load_resources()

    app.add_directive_to_domain(
        'py', 'c7n-schema', CustodianSchema)

    app.add_directive_to_domain(
        'py', 'c7n-resource', CustodianResource)
