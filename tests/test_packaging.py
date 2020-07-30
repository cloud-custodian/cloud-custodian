# Copyright 2020 Cloud Custodian Project and Contributors. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import toml
from pathlib import Path
import pytest


@pytest.mark.parametrize("package", [
    "c7n", "c7n_azure", "c7n_gcp", "c7n_kube", "c7n_org",
    "c7n_mailer", "policystream", "c7n_trailcreator",
    "c7n_logexporter", "c7n_sphinxext"])
def test_package_metadata(package):
    try:
        m = __import__(package)
    except ImportError:
        print('error import %s' % package)
        return
    found = False
    for c in [
            Path(m.__file__).parent.parent / 'pyproject.toml',
            Path(m.__file__).parent / 'pyproject.toml']:
        if c.exists():
            found = True
            p = c
    assert found, "could not find pyproject.yaml"
    data = toml.loads(p.read_text())
    md = data['tool']['poetry']
    assert md.get('homepage') == 'https://cloudcustodian.io'
    assert md.get('documentation').startswith('https://cloudcustodian.io/docs')
    assert md.get('repository') == 'https://github.com/cloud-custodian/cloud-custodian'
    assert md.get('license') == 'Apache-2.0'
    assert md.get('authors') == ['Cloud Custodian Project']
    assert md.get('classifiers', []) == [
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Distributed Computing']
    assert md.get('readme', '').endswith('md')
    assert (p.parent / md['readme']).exists()
    assert 'description' in md
