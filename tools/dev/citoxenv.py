#!/usr/bin/env python
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os
pyver = os.environ.get('TRAVIS_PYTHON_VERSION', '')
if pyver == '2.7':
    print('py27')
elif pyver == '3.6':
    print('py36')
elif pyver == '3.7':
    print('py37')
