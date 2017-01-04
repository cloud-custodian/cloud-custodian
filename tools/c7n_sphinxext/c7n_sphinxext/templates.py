from __future__ import absolute_import

from jinja2 import Environment, PackageLoader

_env = Environment(loader=PackageLoader('c7n_sphinxext', '_templates'))


TEMPLATE_C7N_SCHEMA = _env.get_template("c7n_schema.rst")
