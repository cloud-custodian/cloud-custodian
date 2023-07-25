#!/usr/bin/env bash
# PKG_DOMAIN, PKG_REPO, and valid aws creds and region as pre-reqs
set -euo pipefail
export CODEARTIFACT_OWNER=`aws sts get-caller-identity --query Account --output text`
export CODEARTIFACT_REPOSITORY_URL=`aws codeartifact get-repository-endpoint --domain $PKG_DOMAIN --domain-owner $CODEARTIFACT_OWNER --repository $PKG_REPO --format pypi --query repositoryEndpoint --output text`
export CODEARTIFACT_AUTH_TOKEN=`aws codeartifact get-authorization-token --domain $PKG_DOMAIN --domain-owner $CODEARTIFACT_OWNER --query authorizationToken --output text`
export CODEARTIFACT_USER=aws

echo TWINE_USERNAME=$CODEARTIFACT_USER >> $GITHUB_ENV
echo TWINE_PASSWORD=$CODEARTIFACT_AUTH_TOKEN >> $GITHUB_ENV

# Note: `aws codeartifact login --tool pip` updates user-level pip settings. As a finer-grained alternative, we can
# build a PyPI index URL and use it only inside our virtual environment.
export PYPI_INDEX_URL="${CODEARTIFACT_REPOSITORY_URL#*//}simple/"
python3 -m pip config --site set global.index-url "$PYPI_INDEX_URL"
