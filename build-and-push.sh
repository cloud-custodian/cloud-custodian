#!/usr/bin/env bash

set -e
#export DOCKER_BUILDKIT=1
#export COMPOSE_DOCKER_CLI_BUILD=0

REGION=eu-west-3
PROFILE=manomano-support
REPO_ID=304971447450

export DOCKER_REGISTRY=$REPO_ID.dkr.ecr.eu-west-3.amazonaws.com
export CUSTODIAN_VERSION="mm-0.9.46.0"
export DOCKER_PUSH=true
export DOCKER_PLATFORMS="linux/arm64"

echo Login to ECR
AWS_PROFILE=$PROFILE AWS_REGION=$REGION aws ecr get-login-password | docker login --username AWS --password-stdin $DOCKER_REGISTRY

echo Docker build both images
docker buildx bake --pull --progress plain -f images.hcl --no-cache
