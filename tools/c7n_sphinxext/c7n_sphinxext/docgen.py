# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import difflib
from functools import partial
import hashlib
import logging
import operator
import os
import sys

import click
import yaml

from docutils import nodes
from docutils.statemachine import ViewList
from docutils.parsers.rst.directives import unchanged

from jinja2 import Environment, PackageLoader

from sphinx.directives import SphinxDirective as Directive
from sphinx.util.nodes import nested_parse_with_titles

from c7n.actions import Action
from c7n.config import Config, Bag
from c7n.filters import Filter
from c7n.manager import ResourceManager
from c7n.schema import (
    ElementSchema, resource_vocabulary, generate as generate_schema)
from c7n.policy import execution, PolicyExecutionMode
from c7n.resources import load_resources
from c7n.provider import clouds
from c7n.loader import PolicyLoader


log = logging.getLogger('c7nsphinx')


def template_underline(value, under="="):
    return len(value) * under


def get_environment(provider):
    env = Environment(loader=PackageLoader('c7n_sphinxext', '_templates'))
    env.globals['underline'] = template_underline
    env.globals['ename'] = ElementSchema.name
    env.globals['edoc'] = ElementSchema.doc
    env.globals['eschema'] = CustodianSchema.render_schema
    env.globals['eperm'] = partial(eperm, provider)
    env.globals['render_resource'] = CustodianResource.render_resource
    return env


def eperm(provider, el, r=None):
    if el.permissions:
        return el.permissions
    element_type = get_element_type(el)
    if r is None or r.type is None:
        # dummy resource type for policy
        if provider == 'aws':
            r = Bag({'type': 'kinesis'})
        elif provider == 'gcp':
            r = Bag({'type': 'instance'})
        elif provider == 'azure':
            r = Bag({'type': 'vm'})
        elif provider == 'awscc':
            r = Bag({'type': 'logs_loggroup'})
        elif provider == 'tencentcloud':
            r = Bag({'type': 'ami'})
        elif provider == 'oci':
            r = Bag({'type': 'instance'})

    # print(f'policy construction lookup {r.type}.{element_type}.{el.type}')

    loader = PolicyLoader(Config.empty())
    pdata = {
        'name': f'permissions-{r.type}',
        'resource': f'{provider}.{r.type}'
    }
    pdata[element_type] = get_element_data(element_type, el)

    try:
        pset = loader.load_data({'policies': [pdata]}, ':mem:', validate=False)
    except Exception:
        eperm.errors.append(el)
        # print(f'error loading {el} as {element_type}:{el.type} error: {e} \n {pdata}')
        return []
    el = get_policy_element(el, list(pset)[0])
    return el.get_permissions()


eperm.errors = []


def get_policy_element(el, p):
    el_type = get_element_type(el)
    el_map = {
        'filters': (
            p.resource_manager.filters and p.resource_manager.filters[0]),
        'actions': (
            p.resource_manager.actions and p.resource_manager.actions[0]),
        'mode': p.get_execution_mode(),
        'resource': p.resource_manager
    }
    return el_map[el_type]


def get_element_data(el_type, el):
    # dictionary form of an example for the policy
    if el_type in ('filters', 'actions'):
        return [{'type': el.type}]
    elif el_type == 'mode':
        return {'type': el.type}
    elif el_type == 'resource':
        return el.type


def get_element_type(el):
    if issubclass(el, Filter):
        el_type = 'filters'
    elif issubclass(el, Action):
        el_type = 'actions'
    elif issubclass(el, PolicyExecutionMode):
        el_type = 'mode'
    elif issubclass(el, ResourceManager):
        el_type = 'resource'
    else:
        raise ValueError(f"unknown element type for {el}")
    return el_type


class SafeNoAliasDumper(yaml.SafeDumper):

    def ignore_aliases(self, data):
        return True


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
        provider_type, _ = resource_path.split('.', 1)
        return cls._render('resource.rst',
            variables=dict(
                provider_name=clouds[provider_type].display_name,
                provider_type=provider_type,
                resource_name="%s.%s" % (provider_type, resource_class.type),
                filters=ElementSchema.elements(resource_class.filter_registry),
                actions=ElementSchema.elements(resource_class.action_registry),
                resource=resource_class))


class CustodianSchema(CustodianDirective):

    option_spec = {'module': unchanged}

    @classmethod
    def render_schema(cls, el):
        return cls._render(
            'schema.rst',
            {'schema_yaml': yaml.dump(
                ElementSchema.schema(cls.definitions, el),
                Dumper=SafeNoAliasDumper,
                default_flow_style=False)})

    def run(self):
        schema_path = self.arguments[0]
        el = self.resolve(schema_path)
        schema_yaml = yaml.safe_dump(
            ElementSchema.schema(self.definitions, el), default_flow_style=False)
        return self._nodify(
            'schema.rst', '<c7n-schema>',
            dict(name=schema_path, schema_yaml=schema_yaml))


def get_provider_modes(provider):
    # little bit messy
    # c7n. prefix ~ aws
    # except pull which is common to all.
    results = []
    module_prefix = "c7n_%s." % provider if provider != "aws" else "c7n."
    pull = None
    for name, klass in execution.items():
        if klass.type == 'pull':
            pull = klass
        if klass.__module__.startswith(module_prefix):
            results.append(klass)
    results = list(sorted(results, key=operator.attrgetter('type')))
    results.insert(0, pull)
    return results


INITIALIZED = False


def init(provider):
    global INITIALIZED
    if INITIALIZED:
        return
    load_resources()
    CustodianDirective.vocabulary = resource_vocabulary()
    CustodianDirective.definitions = generate_schema()['definitions']
    CustodianDirective.env = env = get_environment(provider)
    INITIALIZED = True
    return env


def setup(app):
    # we're no longer a sphinx extension, instead we're
    # a sphinx/rst generator. we need to update our setup.py
    # metadata
    init(None)
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
        import traceback, pdb
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])


def write_modified_file(fpath, content, diff_changes=False):
    content_md5 = hashlib.md5(content.encode('utf8'))
    file_md5 = disk_content = None

    if os.path.exists(fpath):
        with open(fpath, 'rb') as fh:
            disk_content = fh.read()

    if disk_content:
        file_md5 = hashlib.md5(disk_content)
        disk_content = disk_content.decode('utf8')

    if file_md5 and content_md5.hexdigest() == file_md5.hexdigest():
        return False

    if diff_changes and disk_content:
        sys.stdout.writelines(
            difflib.context_diff(
                content.split('\n'),
                disk_content.split('\n'),
                fromfile='a/%s' % fpath, tofile='b/%s' % fpath)
        )

    log.info(f'wrote {fpath}')
    with open(fpath, 'w') as fh:
        fh.write(content)
    return True


def resource_file_name(output_dir, r):
    return os.path.join(
        output_dir, ("%s.rst" % r.type).replace(' ', '-').lower())


def _main(provider, output_dir, group_by):
    """Generate RST docs for a given cloud provider's resources
    """
    env = init(provider)

    logging.basicConfig(level=logging.INFO)
    output_dir = os.path.abspath(output_dir)
    provider_class = clouds[provider]

    # group by will be provider specific, supports nested attributes
    group_by = operator.attrgetter(group_by or "type")

    files = []
    written = 0
    groups = {}

    for r in provider_class.resources.values():
        group = group_by(r)

        # deprecated / removed resources don't have a group by
        if group is None:
            continue
        if not isinstance(group, list):
            group = [group]
        for g in group:
            groups.setdefault(g, []).append(r)

    # Create individual resources pages
    for r in provider_class.resources.values():
        # FIXME / TODO: temporary work arounds for a few types that have recursion
        # in jsonschema on these types.
        if provider == 'awscc' and r.type in (
                'wafv2_rulegroup',
                'wafv2_webacl',
                'amplifyuibuilder_theme',
                'amplifyuibuilder_component',
                'amplifybuilder_component'):
            continue

        # deprecated / removed resources don't have a group by
        group = group_by(r)
        if group is None:
            continue

        rpath = resource_file_name(output_dir, r)
        t = env.get_template('provider-resource.rst')
        written += write_modified_file(
            rpath, t.render(
                provider_name=provider,
                provider_type=provider,
                resource=r),
            diff_changes=not written)

    # Create files for all groups
    for key, group in sorted(groups.items()):
        group = sorted(group, key=operator.attrgetter('type'))
        rpath = os.path.join(
            output_dir, ("group-%s.rst" % key).replace(' ', '-').lower())
        t = env.get_template('provider-group.rst')
        written += write_modified_file(
            rpath,
            t.render(
                provider_name=provider,
                provider_type=provider_class.type,
                key=key,
                resource_files=[os.path.basename(
                    resource_file_name(output_dir, r)) for r in group],
                resources=group))
        files.append(os.path.basename(rpath))

    # Write out common provider filters & actions
    common_actions = {}
    common_filters = {}
    for _, r in sorted(provider_class.resources.items()):
        for f in ElementSchema.elements(r.filter_registry):
            if not f.schema_alias:
                continue
            common_filters[ElementSchema.name(f)] = (f, r)

        for a in ElementSchema.elements(r.action_registry):
            if not a.schema_alias:
                continue
            common_actions[ElementSchema.name(a)] = (a, r)

    fpath = os.path.join(
        output_dir,
        ("%s-common-filters.rst" % provider_class.type.lower()))

    t = env.get_template('provider-common-elements.rst')
    written += write_modified_file(
        fpath,
        t.render(
            provider_name=provider_class.display_name,
            provider_type=provider_class.type,
            element_type='filters',
            elements=[common_filters[k] for k in sorted(common_filters)]))
    files.insert(0, os.path.basename(fpath))

    fpath = os.path.join(
        output_dir,
        ("%s-common-actions.rst" % provider_class.type.lower()))
    t = env.get_template('provider-common-elements.rst')
    written += write_modified_file(
        fpath,
        t.render(
            provider_name=provider_class.display_name,
            provider_type=provider_class.type,
            element_type='actions',
            elements=[common_actions[k] for k in sorted(common_actions)]))
    files.insert(0, os.path.basename(fpath))

    # Write out provider modes
    modes = get_provider_modes(provider)
    mode_path = os.path.join(output_dir, '%s-modes.rst' % provider_class.type.lower())
    t = env.get_template('provider-mode.rst')
    written += write_modified_file(
        mode_path,
        t.render(
            provider_name=provider_class.display_name,
            provider_type=provider_class.type,
            modes=modes))
    files.insert(0, os.path.basename(mode_path))

    # Write out the provider index
    provider_path = os.path.join(output_dir, 'index.rst')
    t = env.get_template('provider-index.rst')
    written += write_modified_file(
        provider_path,
        t.render(
            provider_name=provider_class.display_name,
            provider_type=provider_class.type,
            files=files))

    if eperm.errors:
        log.info("%s permission errors %d", provider.title(), len(eperm.errors))
    if written:
        log.info("%s Wrote %d files", provider.title(), written)
