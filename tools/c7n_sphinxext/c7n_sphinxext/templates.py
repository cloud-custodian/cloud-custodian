from __future__ import absolute_import

from jinja2 import Environment, PackageLoader

_env = Environment(loader=PackageLoader('c7n_sphinxext', '_templates'))


def get_template(template_name):
    return _env.get_template(template_name)
