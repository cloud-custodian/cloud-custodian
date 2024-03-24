# -*- coding: utf-8 -
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Minimal client implementation of statsd protocol

https://github.com/statsd/statsd
"""

import logging
import socket

from .output import metrics_outputs, Metrics

log = logging.getLogger('c7n.statsd')

TAG_DOGSTATSD = (
    "dogstatsd"  # this is also the format for cloudwatch log agent statsd support
)
TAG_LIBRATO = "librato"
TAG_SIGNALFX = "signalfx"
TAG_INFLUXDB = "influxdb"


@metrics_outputs.register('statsd')
class StatsdMetrics(Metrics):
    def __init__(self, ctx, config):
        self.ctx = ctx
        self.statsd = self.get_client(config)

    def get_client(self, config):
        host, port = config.netloc.split(':')
        return StatsdClient(
            host, port, config.get('tag_format', TAG_DOGSTATSD)
        ).connect()

    def get_dimensions(self, dimensions):
        if self.ctx.options.account_id:
            dimensions['Account'] = self.ctx.options.account_id
        if self.ctx.options.region:
            dimensions['Region'] = self.ctx.options.region
        dimensions['Policy'] = self.ctx.policy.name
        dimensions['Resource'] = self.ctx.policy.resource_type
        return dimensions

    def put_metric(self, key, value, unit, buffer=False, **dimensions):
        self.statsd.set_tags(self.get_dimensions(dimensions))
        self.statsd.gauge(key, value)

    def flush(self):
        # no client side buffering on statsd
        return


class StatsdClient:
    """statsd client"""

    def __init__(self, host, port, tag_format=TAG_DOGSTATSD, prefix="c7n.policy."):
        self.prefix = prefix
        self.tags = None
        self.sock = None
        self.host = host
        self.port = port
        self.tag_format = TAG_DOGSTATSD

    def set_tags(self, tags):
        self.tags = tags

    # statsd methods
    def gauge(self, name, value):
        self._send(f"{self.prefix}{name}:{value}|g")

    def increment(self, name, value, sampling_rate=1.0):
        # counter++
        self._send(f"{self.prefix}{name}:{value}|c|@{sampling_rate}")

    def decrement(self, name, value, sampling_rate=1.0):
        # counter--
        self._send(f"{self.prefix}{name}:-{value}|c|@{sampling_rate}")

    def histogram(self, name, value):
        self._send(f"{self.prefix}{name}:{value}|ms")

    def set(self, name, value):
        self._send(f"{self.prefix}{name}:{value}|s")

    # internals
    def format_tags(self, msg):
        if not self.tags:
            return msg

        # This is a good overview of the different formats
        # https://github.com/prometheus/statsd_exporter#tagging-extensions

        if self.tag_format == TAG_DOGSTATSD:
            msg += '|#%s' % (",".join(["%s:%s" % (k, v) for k, v in self.tags.items()]))
            return msg
        midx = msg.index(':')
        if self.tag_format == TAG_LIBRATO:
            msg = msg[:midx] + "#%s%s" % (
                ",".join(["%s:%s" % (k, v) for k, v in self.tags.items()]),
                msg[midx:],
            )
        elif self.tag_format == TAG_INFLUXDB:
            msg = msg[:midx] + ",%s%s" % (
                ",".join(["%s:%s" % (k, v) for k, v in self.tags.items()]),
                msg[midx:],
            )
        elif self.tag_format == TAG_SIGNALFX:
            msg = msg[:midx] + "[%s]%s" % (
                ",".join(["%s:%s" % (k, v) for k, v in self.tags.items()]),
                msg[midx:],
            )
        return msg

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.connect((self.host, int(self.port)))
        except Exception:
            log.warning("Couldnt connect to statsd host")
            self.sock = None
        return self

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def _send(self, msg):
        if not self.sock:
            return
        msg = self.format_tags(msg).encode('ascii')
        try:
            self.sock.send(msg)
        except Exception:
            log.warning(self, "Error sending message to statsd", exc_info=True)
