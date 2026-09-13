# https://just.systems/
set dotenv-load := false

@_default:
    just --list

# Install all dependencies (dev, addons, lint groups; gcp + azure extras).
@install:
    uv sync --all-packages --locked \
        --group dev \
        --group addons \
        --group lint \
        --extra gcp --extra azure

# Remove all build artefacts (docs + packages).
@clean:
    just docs clean
    just pkg clean

mod analyzer "just/analyzer.just"
mod data     "just/data.just"
mod docker   "just/docker.just"
mod docs     "just/docs.just"
mod pkg      "just/pkg.just"
mod python   "just/python.just"
