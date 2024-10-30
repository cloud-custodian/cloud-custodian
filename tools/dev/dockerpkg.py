# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
"""
Build Docker Artifacts

On build this is loosely modeled after https://github.com/docker/build-push-action
  - same in that we auto add labels from github action metadata.
  - differs in that we use `dev` for latest.
  - differs in that latest refers to last tagged revision.

We also support running functional tests and image cve scanning before pushing.
"""

import logging
import os
import time
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

import click

log = logging.getLogger("dockerpkg")

PHASE_1_INSTALL_TMPL = """
ADD tools/c7n_{pkg}/pyproject.toml tools/c7n_{pkg}/poetry.lock /src/tools/c7n_{pkg}/
RUN if [[ " ${{providers[*]}} " =~ "{pkg}" ]]; then \
    . /usr/local/bin/activate && \
    cd tools/c7n_{pkg} && \
    poetry install --without dev --no-root; \
fi
"""

PHASE_2_INSTALL_TMPL = """
ADD tools/c7n_{pkg} /src/tools/c7n_{pkg}
RUN if [[ " ${{providers[*]}} " =~ "{pkg}" ]]; then \
    . /usr/local/bin/activate && \
    cd tools/c7n_{pkg} && \
    poetry install --only-root; \
fi
"""

default_providers = ["gcp", "azure", "kube", "openstack", "tencentcloud", "oci", "awscc"]

PHASE_1_PKG_INSTALL_DEP = """\
# We include `pyproject.toml` and `poetry.lock` first to allow
# cache of dependency installs.
"""
PHASE_2_PKG_INSTALL_ROOT = """\
# Now install the root of each provider
"""
PHASE_1_PKG_INSTALL_DEP += "\n".join(
    [PHASE_1_INSTALL_TMPL.format(pkg=pkg) for pkg in default_providers]
)

PHASE_2_PKG_INSTALL_ROOT += "\n".join(
    [PHASE_2_INSTALL_TMPL.format(pkg=pkg) for pkg in default_providers]
)


BOOTSTRAP_STAGE = """\
# Dockerfiles are generated from tools/dev/dockerpkg.py
FROM {base_build_image} AS build-env

ARG POETRY_VERSION="1.8.3"
SHELL ["/bin/bash", "-c"]

# pre-requisite distro deps, and build env setup
RUN apt-get --yes update
RUN apt-get --yes install --no-install-recommends build-essential \
    curl python3-venv python3-dev adduser
# todo: 24.04 is trying to standardize on ubuntu as builtin non root.
RUN adduser --disabled-login --gecos "" custodian
RUN python3 -m venv /usr/local
RUN /usr/local/bin/pip install -U pip setuptools && \
    /usr/local/bin/pip install "poetry=={poetry_version}"
ARG PATH="/root/.local/bin:$PATH"

WORKDIR /src
"""

LEFT_BUILD_STAGE = BOOTSTRAP_STAGE + """\
ADD pyproject.toml poetry.lock README.md /src
RUN . /usr/local/bin/activate && poetry install --only main --no-root

ADD c7n /src/c7n/
RUN . /usr/local/bin/activate && poetry install --only-root

ADD tools/c7n_left /src/tools/c7n_left
RUN . /usr/local/bin/activate && cd tools/c7n_left && poetry install --only main

RUN mkdir /output
"""

BUILD_STAGE = BOOTSTRAP_STAGE + """\
# Add core & aws packages
ADD pyproject.toml poetry.lock README.md /src/
RUN . /usr/local/bin/activate && pip install -qU pip wheel aws-xray-sdk psutil jsonpatch

# Ignore root first pass so if source changes we don't have to invalidate
# dependency install
RUN . /usr/local/bin/activate && poetry install --without dev --no-root

# Now install the root package, we used to do this after dependencies of other providers
# but since moving c7n to a main dependency in pyproject toml we have to do this one first.
ADD c7n /src/c7n/
RUN . /usr/local/bin/activate && poetry install --only-root

ARG providers="{providers}"
# Add provider packages
{PHASE_1_PKG_INSTALL_DEP}

{PHASE_2_PKG_INSTALL_ROOT}

# Install c7n_awscc
ADD tools/c7n_awscc /src/tools/c7n_awscc
RUN . /usr/local/bin/activate && cd tools/c7n_awscc && poetry install

RUN mkdir /output
"""

TARGET_UBUNTU_STAGE = """\
FROM {base_target_image}

LABEL name="{name}" \\
      repository="http://github.com/cloud-custodian/cloud-custodian"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get --yes update \\
        && apt-get --yes install python3 python3-venv adduser {packages} --no-install-recommends \\
        && rm -Rf /var/cache/apt \\
        && rm -Rf /var/lib/apt/lists/* \\
        && rm -Rf /var/log/*

# These should remain below any other commands because they will invalidate
# the layer cache
COPY --from=build-env /src /src
COPY --from=build-env /usr/local /usr/local
COPY --from=build-env /output /output


RUN adduser --disabled-login --gecos "" custodian
USER custodian
WORKDIR /home/custodian
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/home/custodian"]
ENTRYPOINT ["{entrypoint}"]
CMD ["--help"]
"""


TARGET_DISTROLESS_STAGE = """\
FROM {base_target_image}

LABEL name="{name}" \\
      repository="http://github.com/cloud-custodian/cloud-custodian"

COPY --from=build-env /src /src
COPY --from=build-env /usr/local /usr/local
COPY --from=build-env /etc/passwd /etc/passwd
COPY --from=build-env /etc/group /etc/group
COPY --chown=custodian:custodian --from=build-env /output /output
COPY --chown=custodian:custodian --from=build-env /home/custodian /home/custodian

USER custodian
WORKDIR /home/custodian
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/home/custodian"]
ENTRYPOINT ["{entrypoint}"]
CMD ["--help"]
"""

TARGET_CLI = """\
LABEL "org.opencontainers.image.title"="cli"
LABEL "org.opencontainers.image.description"="Cloud Management Rules Engine"
LABEL "org.opencontainers.image.documentation"="https://cloudcustodian.io/docs"
"""

TARGET_LEFT = """
LABEL "org.opencontainers.image.title"="left"
LABEL "org.opencontainers.image.description"="Cloud Custodian IaC Engine"
LABEL "org.opencontainers.image.documentation"="https://cloudcustodian.io/docs/tools/c7n-left.html"
"""

BUILD_KUBE = """\
# Install c7n-kube
ADD tools/c7n_kube /src/tools/c7n_kube
RUN . /usr/local/bin/activate && cd tools/c7n_kube && poetry install
"""

TARGET_KUBE = """\
LABEL "org.opencontainers.image.title"="kube"
LABEL "org.opencontainers.image.description"="Cloud Custodian Kubernetes Hooks"
LABEL "org.opencontainers.image.documentation"="https://cloudcustodian.io/docs"
"""

BUILD_ORG = """\
# Install c7n-org
ADD tools/c7n_org /src/tools/c7n_org
RUN . /usr/local/bin/activate && cd tools/c7n_org && poetry install
"""

TARGET_ORG = """\
LABEL "org.opencontainers.image.title"="org"
LABEL "org.opencontainers.image.description"="Cloud Custodian Management Rules Engine"
LABEL "org.opencontainers.image.documentation"="https://cloudcustodian.io/docs"
"""

BUILD_MAILER = """\
# Install c7n-mailer
ADD tools/c7n_mailer /src/tools/c7n_mailer
RUN . /usr/local/bin/activate && cd tools/c7n_mailer && poetry install --all-extras

"""

TARGET_MAILER = """\
LABEL "org.opencontainers.image.title"="mailer"
LABEL "org.opencontainers.image.description"="Cloud Custodian Notification Delivery"
LABEL "org.opencontainers.image.documentation"="https://cloudcustodian.io/docs"
"""

BUILD_POLICYSTREAM = """\
# Install c7n-policystream
ADD tools/c7n_policystream /src/tools/c7n_policystream
RUN . /usr/local/bin/activate && cd tools/c7n_policystream && poetry install
"""

TARGET_POLICYSTREAM = """\
LABEL "org.opencontainers.image.title"="policystream"
LABEL "org.opencontainers.image.description"="Custodian policy changes streamed from Git"
LABEL "org.opencontainers.image.documentation"="https://cloudcustodian.io/docs"
"""

BUILD_AWSCC = """\
# Install c7n-awscc
ADD tools/c7n_awscc /src/tools/c7n_awscc
RUN . /usr/local/bin/activate && cd tools/c7n_awscc && poetry install
"""


class Image:

    defaults = dict(
        base_build_image="ubuntu:24.04",
        base_target_image="ubuntu:24.04",
        poetry_version="${POETRY_VERSION}",
        packages="",
        providers=" ".join(default_providers),
        PHASE_1_PKG_INSTALL_DEP=PHASE_1_PKG_INSTALL_DEP,
        PHASE_2_PKG_INSTALL_ROOT=PHASE_2_PKG_INSTALL_ROOT,
    )

    def __init__(self, metadata, build, target):
        self.metadata = metadata
        self.build = build
        self.target = target

    @property
    def repo(self):
        return self.metadata.get("repo", self.metadata["name"])

    @property
    def tag_prefix(self):
        return self.metadata.get("tag_prefix", "")

    def render(self):
        output = []
        output.extend(self.build)
        output.extend(self.target)
        template_vars = dict(self.defaults)
        template_vars.update(self.metadata)
        return "\n".join(output).format(**template_vars)

    def clone(self, metadata, target=None):
        d = dict(self.metadata)
        d.update(metadata)
        return Image(d, self.build, target or self.target)


ImageMap = {
    "docker/c7n": Image(
        dict(
            name="cli",
            repo="c7n",
            description="Cloud Management Rules Engine",
            entrypoint="/usr/local/bin/custodian",
        ),
        build=[BUILD_STAGE],
        target=[TARGET_UBUNTU_STAGE, TARGET_CLI],
    ),
    "docker/c7n-kube": Image(
        dict(
            name="kube",
            repo="c7n",
            description="Cloud Custodian Kubernetes Hooks",
            entrypoint="/usr/local/bin/c7n-kates",
        ),
        build=[BUILD_STAGE, BUILD_KUBE],
        target=[TARGET_UBUNTU_STAGE, TARGET_KUBE],
    ),
    "docker/c7n-org": Image(
        dict(
            name="org",
            repo="c7n-org",
            description="Cloud Custodian Organization Runner",
            entrypoint="/usr/local/bin/c7n-org",
        ),
        build=[BUILD_STAGE, BUILD_ORG],
        target=[TARGET_UBUNTU_STAGE, TARGET_ORG],
    ),
    "docker/mailer": Image(
        dict(
            name="mailer",
            description="Cloud Custodian Notification Delivery",
            entrypoint="/usr/local/bin/c7n-mailer",
        ),
        build=[BUILD_STAGE, BUILD_MAILER],
        target=[TARGET_UBUNTU_STAGE, TARGET_MAILER],
    ),
    "docker/policystream": Image(
        dict(
            name="policystream",
            description="Custodian policy changes streamed from Git",
            entrypoint="/usr/local/bin/c7n-policystream",
        ),
        build=[BUILD_STAGE, BUILD_POLICYSTREAM],
        target=[TARGET_UBUNTU_STAGE, TARGET_POLICYSTREAM],
    ),
}


def human_size(size, precision=2):
    # interesting discussion on 1024 vs 1000 as base
    # https://en.wikipedia.org/wiki/Binary_prefix
    suffixes = ["B", "KB", "MB", "GB", "TB", "PB"]
    suffixIndex = 0
    while size > 1024:
        suffixIndex += 1
        size = size / 1024.0

    return "%.*f %s" % (precision, size, suffixes[suffixIndex])


@click.group()
def cli():
    """Custodian Docker Packaging Tool

    slices, dices, and blends :-)
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s:%(levelname)s %(message)s"
    )
    logging.getLogger("docker").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.INFO)

    for name, image in list(ImageMap.items()):
        ImageMap[name + "-distroless"] = image.clone(
            dict(
                tag_prefix="distroless-",
                base_build_image="debian:10-slim",
                base_target_image="gcr.io/distroless/python3-debian10",
            ),
            target=[TARGET_DISTROLESS_STAGE],
        )


@cli.command()
@click.option("-p", "--provider", multiple=True)
@click.option(
    "-r", "--registry", multiple=True, help="Registries for image repo on tag and push"
)
@click.option("-t", "--tag", help="Static tag for the image")
@click.option("--push", is_flag=True, help="Push images to registries")
@click.option(
    "--test", help="Run lightweight functional tests with image", is_flag=True
)
@click.option("--scan", help="scan the image for cve with trivy", is_flag=True)
@click.option("-q", "--quiet", is_flag=True)
@click.option("-i", "--image", multiple=True)
@click.option("-v", "--verbose", is_flag=True)
def build(provider, registry, tag, image, quiet, push, test, scan, verbose):
    """Build custodian docker images...

    python tools/dev/dockerpkg.py --test -i cli -i org -i mailer
    """
    try:
        import docker
    except ImportError as e:
        print("import error %s" % e)
        traceback.print_exc()
        print("python docker client library required")
        print("python %s" % ("\n".join(sys.path)))
        sys.exit(1)
    if quiet:
        logging.getLogger().setLevel(logging.WARNING)
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    client = docker.from_env()

    # Nomenclature wise these are the set of version tags, independent
    # of registry / repo name, that will be applied to all images.
    #
    # ie. Build out some common suffixes for the image
    #
    # Note there's a bit of custodian specific logic in how we get env tags.
    # see the function docstring for more details.
    image_tags = get_env_tags(tag)

    build_args = None
    if provider not in (None, ()):
        build_args = {"providers": " ".join(sorted(provider))} if provider else []

    for path, image_def in ImageMap.items():
        _, image_name = path.split("/")
        if image and image_name not in image:
            continue
        image_id = build_image(client, image_name, image_def, path, build_args)
        image_refs = tag_image(client, image_id, image_def, registry, image_tags)
        if test:
            test_image(image_id, image_name, provider)
        if scan:
            scan_image(":".join(image_refs[0]))
        if push:
            retry(3, (RuntimeError,), push_image, client, image_id, image_refs)


def get_labels(image):
    hub_env = get_github_env()
    # Standard Container Labels / Metadata
    # https://github.com/opencontainers/image-spec/blob/master/annotations.md
    labels = {
        "org.opencontainers.image.created": datetime.utcnow().isoformat(),
        "org.opencontainers.image.licenses": "Apache-2.0",
        "org.opencontainers.image.documentation": "https://cloudcustodian.io/docs",
        "org.opencontainers.image.title": image.metadata["name"],
        "org.opencontainers.image.description": image.metadata["description"],
    }

    if not hub_env:
        hub_env = get_git_env()

    if hub_env.get("repository"):
        labels["org.opencontainers.image.source"] = hub_env["repository"]
    if hub_env.get("sha"):
        labels["org.opencontainers.image.revision"] = hub_env["sha"]
    return labels


def retry(retry_count, exceptions, func, *args, **kw):
    attempts = 1
    while attempts <= retry_count:
        try:
            return func(*args, **kw)
        except exceptions:
            log.warn('retrying on %s' % func)
            attempts += 1
            time.sleep(5)
            if attempts > retry_count:
                raise


def get_github_env():
    envget = os.environ.get
    return {
        k: v
        for k, v in {
            "sha": envget("GITHUB_SHA"),
            "event": envget("GITHUB_EVENT_NAME"),
            "repository": envget("GITHUB_REPOSITORY"),
            "workflow": envget("GITHUB_WORKFLOW"),
            "actor": envget("GITHUB_ACTOR"),
            "event_path": envget("GITHUB_EVENT_PATH"),
            "workspace": envget("GITHUB_WORKSPACE"),
            "actions": envget("GITHUB_ACTIONS"),
            "ref": envget("GITHUB_REF"),
        }.items()
        if v
    }


def get_git_env():
    return {
        "sha": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf8"),
        "repository": "https://github.com/cloud-custodian/cloud-custodian",
    }


def get_image_repo_tags(image, registries, tags):
    results = []
    # get a local tag with name
    if not registries:
        registries = [""]
    for t in tags:
        for r in registries:
            results.append((f"{r}/{image.repo}".lstrip("/"), image.tag_prefix + t))
    return results


def get_env_tags(cli_tag):
    """So we're encoding quite a bit of custodian release workflow logic here.

    Github actions product -dev and release images from same action workflow.

    Azure pipelines runs functional tests and produces nightly images.

    End result is intended to be

    |name|label|frequency|mutability|testing|
    |----|-----|---------|----------|-------|
    |c7n |latest |release |mutable |light-functional|
    |c7n |0.9.1 |release |immutable |light-functional|
    |c7n |nightly |daily |mutable |functional|
    |c7n |2020-04-01 |daily |immutable |functional|
    |c7n |dev |per-commit |mutable |light-functional|
    |c7n |distroless-dev |per-commit|mutable |light-functional|
    |c7n |distroless-latest |release |mutable |functional|
    |c7n |distroless-2020-04-01 |daily |immutable |functional|
    |c7n |distroless-0.9.1 |release |immutable |light-functional|

    This function encodes that the github logic by checking github env vars
    if passed --tag=auto on the cli to distinguish dev/release images.

    It also handles the azure workflow by checking for --tag=nightly and
    adding a date tag.
    """
    image_tags = []
    hub_env = get_github_env()

    if "ref" in hub_env and cli_tag == "auto":
        _, rtype, rvalue = hub_env["ref"].split("/", 2)
        if rtype == "tags":
            image_tags.append("latest")
            image_tags.append(rvalue)
        elif rtype == "heads" and rvalue == "master":
            image_tags.append("dev")
        elif rtype == "heads":  # branch
            image_tags.append(rvalue)

    if cli_tag == "nightly":
        image_tags.append(cli_tag)
        image_tags.append(datetime.utcnow().strftime("%Y-%m-%d"))

    if cli_tag not in ("nightly", "auto"):
        image_tags = [cli_tag]

    return list(filter(None, image_tags))


def tag_image(client, image_id, image_def, registries, env_tags):
    image = client.images.get(image_id)
    image_tags = get_image_repo_tags(image_def, registries, env_tags)
    for repo, tag in image_tags:
        image.tag(repo, tag)
    return image_tags


def scan_image(image_ref):
    cmd = ["trivy"]
    hub_env = get_github_env()
    if "workspace" in hub_env:
        cmd = [os.path.join(hub_env["workspace"], "bin", "trivy")]
    cmd.append(image_ref)
    subprocess.check_call(cmd, stderr=subprocess.STDOUT)


def test_image(image_id, image_name, providers):
    env = dict(os.environ)
    env.update(
        {
            "TEST_DOCKER": "yes",
            "CUSTODIAN_%s_IMAGE"
            % image_name.upper().split("-", 1)[0]: image_id.split(":")[-1],
        }
    )
    if providers not in (None, ()):
        env["CUSTODIAN_PROVIDERS"] = " ".join(providers)
    subprocess.check_call(
        [Path(sys.executable).parent / "pytest", "-p",
         "no:terraform", "-v", "tests/test_docker.py"],
        env=env,
        stderr=subprocess.STDOUT,
    )


def push_image(client, image_id, image_refs):
    if "HUB_TOKEN" in os.environ and "HUB_USER" in os.environ:
        log.info("docker hub login %s" % os.environ["HUB_USER"])
        result = client.login(os.environ["HUB_USER"], os.environ["HUB_TOKEN"])
        if result.get("Status", "") != "Login Succeeded":
            raise RuntimeError("Docker Login failed %s" % (result,))

    for (repo, tag) in image_refs:
        log.info(f"Pushing image {repo}:{tag}")
        for line in client.images.push(repo, tag, stream=True, decode=True):
            if "status" in line:
                log.debug("%s id:%s" % (line["status"], line.get("id", "n/a")))
            elif "error" in line:
                log.warning("Push error %s" % (line,))
                raise RuntimeError("Docker Push Failed\n %s" % (line,))
            else:
                log.info("other %s" % (line,))


def build_image(client, image_name, image_def, dfile_path, build_args):
    log.info("Building %s image (--verbose for build output)" % image_name)

    labels = get_labels(image_def)
    stream = client.api.build(
        path=os.path.abspath(os.getcwd()),
        dockerfile=dfile_path,
        buildargs=build_args,
        labels=labels,
        rm=True,
        pull=True,
        decode=True,
    )

    built_image_id = None
    for chunk in stream:
        if "stream" in chunk:
            log.debug(chunk["stream"].strip())
        elif "status" in chunk:
            log.debug(chunk["status"].strip())
        elif "aux" in chunk:
            built_image_id = chunk["aux"].get("ID")
    assert built_image_id
    if built_image_id.startswith("sha256:"):
        built_image_id = built_image_id[7:]

    built_image = client.images.get(built_image_id)
    log.info(
        "Built %s image Id:%s Size:%s"
        % (image_name, built_image_id[:12], human_size(built_image.attrs["Size"]),)
    )

    return built_image_id[:12]


@cli.command()
def generate():
    """Generate dockerfiles"""
    for df_path, image in ImageMap.items():
        print(df_path)
        p = Path(df_path)
        p.write_text(image.render())


if __name__ == "__main__":
    cli()
