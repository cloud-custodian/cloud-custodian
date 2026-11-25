set working-directory := ".."

@_default:
    just --list docker

IMAGE     := env_var_or_default("IMAGE", "c7n")
IMAGE_TAG := env_var_or_default("IMAGE_TAG", "latest")

# Build the Docker image (IMAGE=c7n IMAGE_TAG=latest).
@build:
    docker build -f docker/{{IMAGE}} -t {{IMAGE}}:{{IMAGE_TAG}} .

# Regenerate Dockerfiles from the template script.
@gen:
    uv run tools/dev/dockerpkg.py generate
