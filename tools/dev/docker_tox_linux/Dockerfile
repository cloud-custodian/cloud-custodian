# Build and run this with context set to the root of the repository.
#
# For standard py37 tox, change working directory to the repository root and run:
# docker build -t tox_linux . -f tools/dev/docker_tox_linux/Dockerfile && docker run -it tox_linux
#
# If you'd like to run sphinx docs and see the HTML output, add a volume for the HTML output and an ARG to the build.
# For example:
# docker build -t tox_linux --build-arg TOX_ENV=docs . -f tools/dev/docker_tox_linux/Dockerfile
# docker run -v local_path_to_save_docs:/src/docs/build -it tox_linux


FROM python:3.7-stretch

LABEL name="custodian tox" \
      description="Run Custodian test suite" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="http://github.com/cloud-custodian/cloud-custodian" \
      maintainer="Custodian Community <https://cloudcustodian.io>"

RUN pip3 install tox

ADD . /src
WORKDIR /src
RUN tox -e py37 --notest

ARG TOX_ENV=py37

# Setup for EntryPoint
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8" TOX_ENV_ENV=$TOX_ENV
ENTRYPOINT tox -e $TOX_ENV_ENV
