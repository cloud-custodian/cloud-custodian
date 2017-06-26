#!/usr/bin/env python
import os
pyver = os.environ.get('TRAVIS_PYTHON_VERSION', '')
if pyver == '2.7':
    print('py27-cov,docs,lint')
elif pyver == '3.6':
    print('py36')
