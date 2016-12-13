from __future__ import absolute_import

from jinja2 import Environment, PackageLoader

_env = Environment(loader=PackageLoader('tools.sphinxext', '_templates'))


TEMPLATE_C7N_SCHEMA = _env.get_template("c7n_schema.rst")
