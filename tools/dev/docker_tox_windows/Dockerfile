# This is a Windows container and must run in Windows.
# Build and run this with context set to the root of the repository.
#
# Change working directory to the repository root and run:
# docker build -t custodian_tox_win . -f tools/dev/docker_tox_windows/Dockerfile && docker run -it custodian_tox_win

FROM python:3.8-windowsservercore

LABEL name="custodian tox windows" \
      description="Run Custodian test suite" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="http://github.com/cloud-custodian/cloud-custodian" \
      maintainer="Custodian Community <https://cloudcustodian.io>"

RUN pip3 install tox

ADD . /src

# Setup for EntryPoint
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
WORKDIR /src
ENTRYPOINT ["tox", "-e", "py38"]
