#!/usr/bin/env bash
# PKG_DOMAIN, PKG_REPO, and valid aws creds and region as pre-reqs
set -euxo pipefail
export CODEARTIFACT_OWNER=`aws sts get-caller-identity --query Account --output text`
export CODEARTIFACT_REPOSITORY_URL=`aws codeartifact get-repository-endpoint --domain $PKG_DOMAIN --domain-owner $CODEARTIFACT_OWNER --repository $PKG_REPO --format pypi --query repositoryEndpoint --output text`
export CODEARTIFACT_AUTH_TOKEN=`aws codeartifact get-authorization-token --domain $PKG_DOMAIN --domain-owner $CODEARTIFACT_OWNER --query authorizationToken --output text`
export CODEARTIFACT_USER=aws

echo TWINE_USERNAME=$CODEARTIFACT_USER >> $GITHUB_ENV
echo TWINE_PASSWORD=$CODEARTIFACT_AUTH_TOKEN >> $GITHUB_ENV
echo STAGE_INDEX_URL="https://${CODEARTIFACT_USER}:${CODEARTIFACT_AUTH_TOKEN}@${CODEARTIFACT_REPOSITORY_URL#*//}simple/" >> $GITHUB_ENV

# Note: `aws codeartifact login --tool pip` updates user-level pip settings. As a finer-grained alternative, we can
# build a PyPI index URL and use it only inside our virtual environment.

# uv run python -m pip config --site set global.index-url "$CODEARTIFACT_REPOSITORY_URL"


cat <<EOF >> $HOME/.pypirc
[distutils]
index-servers = 
        pypi
        stagec7n

[stagec7n]
repository = $CODEARTIFACT_REPOSITORY_URL
username = $CODEARTIFACT_USER
password = $CODEARTIFACT_AUTH_TOKEN
EOF
