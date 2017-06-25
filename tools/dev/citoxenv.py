#!/usr/bin/env python
import os
pyenv = "py%s-cov" % (os.environ.get(
    'TRAVIS_PYTHON_VERSION', '').replace('python', 'py').replace('.', ''))
toxenv = [pyenv]
if pyenv == 'py27-cov':
    toxenv.append('docs')
    toxenv.append('lint')
print(",".join(toxenv))
