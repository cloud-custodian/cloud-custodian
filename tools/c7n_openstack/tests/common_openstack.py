# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from functools import partial
import os

import vcr

from c7n.testing import TestUtils
from c7n.resources import load_resources

from c7n_openstack.client import Session


load_resources()

OPENSTACK_CONFIG = {
    'OS_USERNAME': 'c7n',
    'OS_PASSWORD': 'secret',
    'OS_REGION_NAME': 'RegionOne',
    'OS_AUTH_URL': 'http://keystone:5000/v3',
    'OS_PROJECT_NAME': 'c7n-test',
    'OS_USER_DOMAIN_NAME': 'Default',
    'OS_PROJECT_DOMAIN_NAME': 'Default',
    'OS_IDENTITY_API_VERSION': '3',
    'OS_CLOUD_NAME': 'c7n-cloud',
}

DEFAULT_CASSETTE_FILE = "default.yaml"


def init_openstack_config():
    for k, v in OPENSTACK_CONFIG.items():
        os.environ[k] = v


class OpenStackTest(TestUtils):

    init_openstack_config()
    recording = False

    def replay_flight_data(self, name=None):
        kw = self._get_vcr_kwargs()
        kw['record_mode'] = 'any'
        self.myvcr = self._get_vcr(**kw)
        cm = self.myvcr.use_cassette(name or self._get_cassette_name(),
                                     allow_playback_repeats=True)
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return partial(Session)

    def record_flight_data(self, name=None):
        kw = self._get_vcr_kwargs()
        kw['record_mode'] = 'all'
        self.myvcr = self._get_vcr(**kw)

        flight_path = os.path.join(
            kw['cassette_library_dir'], name or self._get_cassette_name())
        if os.path.exists(flight_path):
            os.unlink(flight_path)

        cm = self.myvcr.use_cassette(name or self._get_cassette_name())
        self.recording = True
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)

        return Session

    def _get_vcr_kwargs(self):
        return dict(filter_headers=['authorization'],
                    cassette_library_dir=self._get_cassette_library_dir())

    def _get_vcr(self, **kwargs):
        myvcr = vcr.VCR(**kwargs)
        return myvcr

    def _get_cassette_library_dir(self):
        return os.path.join(
            os.path.dirname(__file__),
            'data', 'flights')

    def _get_cassette_name(self):
        cassette_dir = self._get_cassette_library_dir()
        cassette_file = '{0}.{1}.yaml'.format(self.__class__.__name__,
                                              self._testMethodName)
        if os.path.isfile(cassette_dir + '/' + cassette_file):
            return cassette_file
        cassette_file = '{0}.yaml'.format(self.__class__.__name__)
        if os.path.isfile(cassette_dir + '/' + cassette_file):
            return cassette_file
        return DEFAULT_CASSETTE_FILE
