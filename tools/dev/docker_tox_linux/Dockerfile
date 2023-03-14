# Build and run this with context set to the root of the repository.
#
# For standard py37 tox, change working directory to the repository root and run:
# docker build -t tox_linux . -f tools/dev/docker_tox_linux/Dockerfile && docker run -it tox_linux
#
# If you'd like to run sphinx docs and see the HTML output you will add a TOX_ENV arg
# to the `build` and add a volume for the HTML output to the `run`
#
# For example, a useful one-liner to build image and then run doc build to `docs/build`:
#
# Linux:
# docker build -t tox_linux --build-arg TOX_ENV=docs . -f tools/dev/docker_tox_linux/Dockerfile &&
# docker run -v 'pwd'/docs/build:/src/docs/build -it tox_linux
#
# Windows:
# docker build -t tox_linux --build-arg TOX_ENV=docs . -f tools/dev/docker_tox_linux/Dockerfile &&
# docker run -v %cd%/docs/build:/src/docs/build -it tox_linux



FROM python:3.8-buster

LABEL name="custodian tox" \
      description="Run Custodian test suite" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="http://github.com/cloud-custodian/cloud-custodian" \
      maintainer="Custodian Community <https://cloudcustodian.io>"

RUN pip3 install tox

ADD . /src
WORKDIR /src
RUN tox -e py38 --notest

ARG TOX_ENV=py38

# Setup for EntryPoint
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8" TOX_ENV_ENV=$TOX_ENV
ENTRYPOINT tox -e $TOX_ENV_ENV
