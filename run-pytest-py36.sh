#!/usr/bin/env bash

# Wrap py.test to force a 0 exit status for easier integration with tox. We 
# expect tests to fail here, and in tox.ini we run a second script to ensure that
# none of our expected successes are failing.

.tox/py36/bin/py.test -v -n auto --cov=c7n --junitxml=results.xml tests tools
exit 0
