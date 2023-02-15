# Local development

If you are just interested in doing local development with GCP, and not the
whole c7n collection, then you can do the following.

## Install the development dependencies

Poetry will create a virtual environment and install the development dependencies.

    poetry install

## Setup environment keys

Normally tests will be run from the root of the c7n project. You can just run local
ones, but you will need some environment variables. These are set in `test.env` in the
`c7n` project root dir.

    export GOOGLE_CLOUD_PROJECT=custodian-1291
    export GOOGLE_APPLICATION_CREDENTIALS=tests/data/credentials.json

## Running the tests

You want to ensure that you are using the dependencies installed by poetry,
so run the tests with something like this:

    poetry run pytest <other flags>

Some people prefer to use the `poetry shell` functionality to enter the virtual
environment.

    poetry shell
    pytest <flags>

