#!/bin/bash -e
set -x

# Workspace
cd ..

# Install prerequisites
pip3 install -U virtualenv tox

# Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Virtual env
python3 -m venv .venv
source .venv/bin/activate

# Install
make install-poetry
