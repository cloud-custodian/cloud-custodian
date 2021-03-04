#!/bin/bash -e
set -x

# Workspace
cd ..

# Install prerequisites
pip3 install -U virtualenv tox

# Poetry
curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python -
source $HOME/.poetry/env

# Virtual env
python3 -m venv .venv
source .venv/bin/activate

# Install
make install-poetry
