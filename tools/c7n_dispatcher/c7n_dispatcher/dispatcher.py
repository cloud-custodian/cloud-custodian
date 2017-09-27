# Copyright 2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import, division, print_function, unicode_literals

from elasticsearch import Elasticsearch, RequestsHttpConnection

import base64
import json
import logging
import zlib

from c7n import sqsexec
from c7n.actions import Notify
from c7n.registry import PluginRegistry


messengers = PluginRegistry('custodian-dispatcher-messengers')


class Messenger(object):
    """ Dispatcher Messenger
    """


def get_messenger(config):
    klass = messengers.get(config['messenger']['type'])
    return klass(config)


@messengers.register('elasticsearch')
class ElasticSearchMessenger(Messenger):

    def __init__(self, config):
        self.config = config

        host = [config['messenger'].get('host', 'localhost')]
        kwargs = {}
        kwargs['connection_class'] = RequestsHttpConnection
        kwargs['port'] = config['messenger'].get('port', 9200)

        user = config['messenger'].get('user', False)
        password = config['messenger'].get('password', False)
        if user and password:
            kwargs['http_auth'] = (user, password)

        self.client = Elasticsearch(host, **kwargs)

    def send(self, message, logger):
        res = self.client.index(
            index = self.config['messenger']['index'],
            doc_type = message['policy']['resource'],
            body = message
        )
        logger.debug('Sent Message: {} \nGot Response: {}'.format(
            message, res))


class Dispatcher(object):
    """ Send data from SQS queue to config endpoint
    """

    def __init__(self, config, logger, session, max_num_processes=16):
        self.config                = config
        self.logger                = logger
        self.session               = session
        self.max_num_processes     = max_num_processes
        self.receive_queue         = self.config['queue_url']
        self.messenger             = get_messenger(config)
        if self.config.get('debug', False):
            self.logger.debug('debug logging is turned on from dispatcher config file.')
            logger.setLevel(logging.DEBUG)

    def run(self, parallel=False):
        self.logger.info("Downloading messages from the SQS queue.")
        aws_sqs = self.session.client('sqs')
        sqs_messages = sqsexec.MessageIterator(aws_sqs, self.receive_queue, self.logger)
        sqs_messages.msg_attributes = ['mtype']
        # lambda doesn't support multiprocessing, so we don't instantiate any mp stuff
        # unless it's being run from CLI on a normal system with SHM
        if parallel:
            import multiprocessing
            process_pool = multiprocessing.Pool(processes=self.max_num_processes)
        for sqs_message in sqs_messages:
            self.logger.debug(
                "Message id: %s received %s" % (
                    sqs_message['MessageId'], sqs_message.get('MessageAttributes', '')))
            msg_kind = sqs_message.get('MessageAttributes', {}).get('mtype')
            if msg_kind:
                msg_kind = msg_kind['StringValue']
            if not msg_kind == Notify.C7N_DATA_MESSAGE:
                warning_msg = 'Unknown sqs_message format %s' % (sqs_message['Body'][:50])
                self.logger.warning(warning_msg)
            if parallel:
                process_pool.apply_async(self.process_sqs_messsage, args=sqs_message)
            else:
                self.process_sqs_messsage(sqs_message)
            self.logger.debug('Processed sqs_message')
            sqs_messages.ack(sqs_message)
        if parallel:
            process_pool.close()
            process_pool.join()
        self.logger.info('No sqs_messages left on the queue, exiting c7n_dispatcher.')
        return

    def process_sqs_messsage(self, encoded_sqs_message):
        sqs_message = json.loads(zlib.decompress(base64.b64decode(encoded_sqs_message['Body'])))
        self.logger.debug("Got account:{} message:{} {}:{} policy:{}".format(
            sqs_message.get('account', 'N/A'),
            encoded_sqs_message['MessageId'],
            sqs_message['policy']['resource'],
            len(sqs_message['resources']),
            sqs_message['policy']['name']))
        self.messenger.send(sqs_message)
