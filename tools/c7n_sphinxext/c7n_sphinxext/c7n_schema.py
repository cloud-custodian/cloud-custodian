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
from sphinx.util.compat import Directive
from sphinx.util.nodes import nested_parse_with_titles

from .templates import TEMPLATE_C7N_SCHEMA
from c7n.utils import reformat_schema


# taken from Sphinx autodoc
py_sig_re = re.compile(
    r'''^ ([\w.]*\.)?            # class name(s)
          (\w+)  \s*             # thing name
          (?: \((.*)\)           # optional: arguments
           (?:\s* -> \s* (.*))?  #           return annotation
          )? $                   # and nothing more
          ''', re.VERBOSE)


class C7nSchemaDirective(Directive):

    has_content = True
    required_arguments = 1
    optional_arguments = 2

    option_spec = {
        'module': unchanged
    }

    def _parse(self, rst_text, annotation):
        result = ViewList()
        for line in rst_text.split("\n"):
            result.append(line, annotation)
        node = nodes.paragraph()
        node.document = self.state.document
        nested_parse_with_titles(self.state, result, node)
        return node.children

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
            raise SphinxError("Unable to generate reference docs for %s, couldn't import module '%s'" % (model_name, module_name))

        model = getattr(module, model_name, None)
        if model is None:
            raise SphinxError("Unable to generate reference docs for %s, no model '%s' in %s" % (model_name, model_name, module_name))

        if not hasattr(model, 'schema'):
            raise SphinxError("Unable to generate reference docs for %s, model '%s' does not have a 'schema' attribute" % (model_name, model_name))

        schema = reformat_schema(model)

        schema_json = json.dumps(
            schema,
            sort_keys=True,
            indent=2,
            separators=(',', ': ')
        )

        rst_text = TEMPLATE_C7N_SCHEMA.render(
            name=model_name,
            module_name=module_name,
            schema_json=schema_json,
        )

        return self._parse(rst_text, "<c7n-schema>")


def setup(app):
    app.add_directive_to_domain('py', 'c7n-schema', C7nSchemaDirective)
