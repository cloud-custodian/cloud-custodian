# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
# AWS resources to manage
#
import logging

from c7n.provider import clouds

log = logging.getLogger('c7n.resources')

LOADED = set()


def load_resources(resource_types=('*',)):
    pmap = {}
    for r in resource_types:
        parts = r.split('.', 1)
        # support aws.*
        if parts[-1] == '*':
            r = '*'
        pmap.setdefault(parts[0], []).append(r)

    load_providers(set(pmap))
    missing = []
    for pname, p in clouds.items():
        if '*' in pmap:
            p.get_resource_types(('*',))
        elif pname in pmap:
            _, not_found = p.get_resource_types(pmap[pname])
            missing.extend(not_found)
    return missing


def should_load_provider(name, provider_types, no_wild=False):
    global LOADED
    if (name not in LOADED and
        (('*' in provider_types and not no_wild)
         or name in provider_types)):
        return True
    return False


PROVIDER_NAMES = ('aws', 'azure', 'gcp', 'k8s', 'openstack', 'awscc', 'tencentcloud', 'oci', 'terraform')

# the distribution package each provider is implemented in, used to tell an
# uninstalled provider apart from a broken one.
PROVIDER_PACKAGES = {
    'aws': 'c7n',
    'awscc': 'c7n_awscc',
    'azure': 'c7n_azure',
    'gcp': 'c7n_gcp',
    'k8s': 'c7n_kube',
    'oci': 'c7n_oci',
    'openstack': 'c7n_openstack',
    'tencentcloud': 'c7n_tencentcloud',
    'terraform': 'c7n_left',
}


def is_provider_missing(provider, err):
    """Is this ImportError the provider itself being absent?

    Only a ModuleNotFoundError for the provider's top level package counts.
    Anything else - a missing dependency of an installed provider, a typo in
    one of its modules (``c7n_gcp.resources.foo``), a bad ``from x import y``
    - means the provider is installed but broken, which is worth saying out
    loud rather than reporting as "not installed".
    """
    if provider == 'aws':
        # aws lives in c7n itself, if we're running it's installed
        return False
    return isinstance(err, ModuleNotFoundError) and err.name == PROVIDER_PACKAGES[provider]


def load_available(resources=True):
    """Load available installed providers

    Unlike load_resources() this skips providers that fail to import.

    A provider whose own package is absent simply isn't installed, and is
    skipped quietly. A provider that is installed but fails to import -
    a missing dependency, a broken module - is skipped too, but logged at
    warning, so the user finds out why its resource types disappeared. We
    don't raise: every custodian command loads every provider, and one
    broken optional provider shouldn't take down an unrelated policy run.
    """
    found = []
    for provider in PROVIDER_NAMES:
        try:
            load_providers((provider,))
        except ImportError as err:
            if is_provider_missing(provider, err):
                log.debug("provider %s not installed (%s)", provider, err)
            else:
                log.warning(
                    "provider %s is installed but failed to import: %s", provider, err)
            continue
        else:
            found.append(provider)
    if resources:
        load_resources(['%s.*' % s for s in found])
    return found


def load_providers(provider_types):
    global LOADED

    # Even though we're lazy loading resources we still need to import
    # those that are making available generic filters/actions
    if should_load_provider('aws', provider_types):
        import c7n.resources.securityhub
        import c7n.resources.sfn
        import c7n.resources.ssm # NOQA

    if should_load_provider('awscc', provider_types):
        from c7n_awscc.entry import initialize_awscc
        initialize_awscc()

    if should_load_provider('azure', provider_types):
        from c7n_azure.entry import initialize_azure
        initialize_azure()

    if should_load_provider('gcp', provider_types):
        from c7n_gcp.entry import initialize_gcp
        initialize_gcp()

    if should_load_provider('k8s', provider_types):
        from c7n_kube.entry import initialize_kube
        initialize_kube()

    if should_load_provider('openstack', provider_types):
        from c7n_openstack.entry import initialize_openstack
        initialize_openstack()

    if should_load_provider('terraform', provider_types, no_wild=True):
        from c7n_left.entry import initialize_iac
        initialize_iac()

    if should_load_provider('tencentcloud', provider_types):
        from c7n_tencentcloud.entry import initialize_tencentcloud
        initialize_tencentcloud()

    if should_load_provider('oci', provider_types):
        from c7n_oci.entry import initialize_oci
        initialize_oci()

    if should_load_provider('c7n', provider_types):
        from c7n import data  # noqa

    LOADED.update(provider_types)
