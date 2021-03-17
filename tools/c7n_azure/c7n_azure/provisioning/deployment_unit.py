# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

from abc import ABCMeta, abstractmethod

from c7n.utils import local_session
from c7n_azure.session import Session


class DeploymentUnit(metaclass=ABCMeta):
    log = logging.getLogger('custodian.azure.deployment_unit.DeploymentUnit')

    def __init__(self, client):
        self.type = ""
        self.session = local_session(Session)
        self.client = self.session.client(client)

    def get(self, params):
        result = self._get(params)
        if result:
            self.log.info('Found %s "%s".' % (self.type, params['name']))
        else:
            self.log.info('%s "%s" not found.' % (self.type, params['name']))
        return result

    def check_exists(self):
        return self.get() is not None

    def provision(self, params):
        self.log.info('Creating %s "%s"' % (self.type, params['name']))
        result = self._provision(params)
        if result:
            self.log.info('%s "%s" successfully created' % (self.type, params['name']))
        else:
            self.log.info('Failed to create %s "%s"' % (self.type, params['name']))
        return result

    def provision_if_not_exists(self, params):
        result = self.get(params)
        if result is None:
            if 'id' in params.keys():
                raise Exception('%s with %s id is not found' % (self.type, params['id']))
            result = self.provision(params)
        return result

    @abstractmethod
    def _get(self, params):
        raise NotImplementedError()

    @abstractmethod
    def _provision(self, params):
        raise NotImplementedError()
