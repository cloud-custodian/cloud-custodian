# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import click
from collections import Counter
import boto3
import logging
import gzip
import time
import os
import sqlite3

from datetime import timedelta, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from flowrecord import FlowRecord, REJECT
from influxdb import InfluxDBClient

from metrics import Resource
from resolver import IPResolver
from utils import human_size, row_factory, get_dates

from c7n.executor import MainThreadExecutor

EPOCH_32_MAX = 2147483647

MainThreadExecutor.c7n_async = False

log = logging.getLogger('traffic')


def eni_download_flows(client, bucket, prefix, start, end, eni, store_dir):
    # t = time.time()
    # 30m aggregation delay
    # if end:
    #    end_barrier = end + timedelta(seconds=30*60)
    # else:
    #    end_barrier = None
    log_size = count = skip = 0

    eni_path = os.path.join(store_dir, '%s-all' % eni)
    if not os.path.exists(eni_path):
        os.makedirs(eni_path)

    results = client.list_objects_v2(
        Bucket=bucket,
        Prefix="%s/%s" % (
            prefix.rstrip('/'),
            "%s-all" % eni))
    truncated = results['IsTruncated']

    for k in results.get('Contents', ()):
        # if end_barrier and k['LastModified'] > end_barrier:
        #    skip += 1
        #    continue
        # if k['LastModified'] < start:
        #    skip += 1
        #    continue
        dl_key = os.path.join(store_dir, '%s-all' % eni, k['Key'].rsplit('/', 1)[-1])
        log_size += k['Size']
        if os.path.exists(dl_key) and os.path.getsize(dl_key) == k['Size']:
            count += 1
            yield dl_key
            continue
        client.download_file(bucket, k['Key'], dl_key)
        yield dl_key
        count += 1

    log.info("eni:%s logs-skip:%d logs-consumed:%d truncated:%s size:%s" % (
        eni, skip, count, truncated, human_size(log_size)))


def eni_flow_stream(files, start, end, buffer_size=25000):
    buf = []
    record_count = 0
    if start:
        u_start = time.mktime(start.timetuple())
    if end:
        u_end = time.mktime(end.timetuple())
    for f in files:
        with gzip.open(f) as fh:
            while True:
                line = fh.readline()
                if not line:
                    break
                fields = line.split()
                fields.pop(0)
                rstart = int(fields[10])
                if rstart > EPOCH_32_MAX:
                    rstart /= 1000
                rend = int(fields[11])
                if rend > EPOCH_32_MAX:
                    rend /= 1000

                # record windows typically either 60s or 5m
                # print('record window %0.2f' % (record.end - record.start))
                if start and rstart < u_start:
                    continue

                # we might lose a few records if we just record.end < u_end
                if end and rend > u_end:
                    continue

                buf.append(FlowRecord(fields=fields))
                if len(buf) % buffer_size:
                    record_count += len(buf)
                    yield buf
                    buf = []

    if buf:
        record_count += len(buf)
        yield buf


def flow_stream_stats(ips, flow_stream, period):
    period_counters = {}
    stats = Counter()
    for flow_records in flow_stream:
        for record in flow_records:
            stats['Flows'] += 1
            stats['Bytes'] += record.bytes
            pk = record.start - record.start % period
            pc = period_counters.get(pk)
            if pc is None:
                period_counters[pk] = pc = {
                    'inbytes': Counter(), 'outbytes': Counter()}
            if record.action == REJECT:
                stats['Rejects'] += 1
            if record.dstaddr in ips:
                pc['inbytes'][record.srcaddr] += record.bytes
            elif record.srcaddr in ips:
                pc['outbytes'][record.dstaddr] += record.bytes
            else:
                raise ValueError("")
    log.info(
        "flows:%d bytes:%s rejects:%s",
        stats['Flows'], human_size(stats['Bytes']), stats['Rejects'])

    return period_counters


def rollup_logical(counter, lookup, logical_keys):
    logical = Counter()
    for k, v in counter.items():
        # TODO: eek, do a fallback of some kind
        if k not in lookup:
            logical[('unknown', k)] = v
            continue
        linfo = lookup[k]
        lkey = tuple(linfo.get(lk, 'unknown') for lk in logical_keys)
        logical[lkey] += v

    return logical


def process_eni_metrics(
        stream_eni, myips, stream,
        start, end, period, sample_size,
        resolver, sink_uri):
    """ENI flow stream processor that rollups, enhances,
       and indexes the stream by time period."""
    stats = Counter()
    period_counters = flow_stream_stats(myips, stream, period)
    client = InfluxDBClient.from_dsn(sink_uri)
    resource = resolver.resolve_resource(stream_eni)
    points = []

    for period in sorted(period_counters):
        pc = period_counters[period]
        pd = datetime.fromtimestamp(period)

        for t in ('inbytes', 'outbytes'):
            tpc = pc[t]
            ips = [ip for ip, _ in tpc.most_common(sample_size)]
            resolved = resolver.resolve(ips, pd - timedelta(900), pd + timedelta(900))
            logical_counter = rollup_logical(tpc, resolved, ('app', 'env'))
            for (app, env), v in logical_counter.items():
                p = {}
#                rinfo = resolved.get(ip, {})
                p['fields'] = {'Bytes': v}
                p['measurement'] = 'traffic_%s' % t
                p['time'] = datetime.fromtimestamp(period)
                p['tags'] = {
                    'Kind': resource['type'],
                    'AccountId': resource['account_id'],
                    'App': resource['app'],
                    'Env': resource['env'],
                    'ForeignApp': app,
                    'ForeignEnv': env}
                points.append(p)

        if len(points) > 2000:
            client.write_points(points)
            stats['Points'] += len(points)
            points = []

    client.write_points(points)
    stats['Points'] += len(points)
    log.info('periods:%d resource:%s points:%d',
             len(period_counters), resource, stats['Points'])
    return stats


def eni_log_analyze(ips, flow_stream,
                    start=None, end=None,
                    reject=None, target_ips=None,
                    ports=()):

    # in_packets = Counter()
    in_bytes = Counter()
    in_ports = Counter()
    # out_packets = Counter()
    out_bytes = Counter()
    out_ports = Counter()

    # intra_bytes = Counter()
    stats = Counter()
    # reject = 'REJECT'

    for flow_records in flow_stream:
        for record in flow_records:
            stats['Flows'] += 1
            stats['Bytes'] += record.bytes

            if record.action == reject:
                stats['Rejects'] += 1
            # if ports and (record.srcport not in ports and record.dstport not in ports):
            #    continue
            # if reject is not None:
            #    if reject and record.action != 'REJECT':
            #        continue
            #    if reject is False and record.action != 'ACCEPT':
            #        continue
            # if target_ips:
            #    if not (record.dstaddr in target_ips or
            #                record.srcaddr in target_ips):
            #        continue
            # if record.dstaddr in ips and record.srcaddr in ips:
            #    intra_bytes[record.srcaddr] += record.bytes
            if record.dstaddr in ips:
                # in_packets[record.srcaddr] += record.packets
                in_bytes[record.srcaddr] += record.bytes
                # if record.srcaddr not in ips:
                #    in_ports[record.srcport] += record.bytes
            elif record.srcaddr in ips:
                # out_packets[record.dstaddr] += record.packets
                out_bytes[record.dstaddr] += record.bytes
                # out_ports[record.dstport] += record.bytes
            else:
                raise ValueError("")

    log.info(
        "records:%d rejects:%d inbytes:%s outbytes:%s bytes:%s",
        stats['Flows'],
        stats['Rejects'],
        human_size(sum(in_bytes.values())),
        human_size(sum(out_bytes.values())),
        human_size(stats['Bytes']))

    return in_bytes, out_bytes, in_ports, out_ports


def resolve_ip_address(counter, resolver, start, end):
    resolved = resolver.resolve(counter.keys(), start, end)
    log.info("Resolved %d of %d ips", len(resolved), len(counter.keys()))
    for k in list(counter):
        i = resolved.get(k)
        if i is not None:
            v = counter.pop(k)
            counter['%s %s' % (k, (
                " ".join(["%s:%s" % (ik, iv) for ik, iv in i.items() if iv]).strip()))] += v
    return counter


@click.group()
def cli():
    """Flow Log Analyzer"""


@cli.command('load-app-flow')
@click.option('--account-id')
@click.option('--app')
@click.option('--env')
@click.option('--bucket')
@click.option('--prefix')
@click.option('--store-dir')
@click.option('--ipdb')
@click.option('--ipranges', type=click.Path())
@click.option('--start')
@click.option('--end')
@click.option('--tz')
@click.option('--sink')
@click.option('--debug', is_flag=True, default=False)
@click.option('--sample-count', default=20)
@click.option('--period', default=300)
@click.option(
    '-r', '--resources', multiple=True,
    type=click.Choice(['Instance', 'LoadBalancer', 'Volume']))
def analyze_app(
        app, env, account_id,
        bucket, prefix, store_dir,
        resources, ipdb, ipranges,
        start, end, tz,
        sink, period, sample_count,
        debug):
    """Analyze flow log records for application and generate metrics per period"""
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('botocore').setLevel(logging.WARNING)

    executor = debug and MainThreadExecutor or ThreadPoolExecutor
    start, end = get_dates(start, end, tz)
    resolver = IPResolver(ipdb, ipdb, ipranges)

    for rtype_name in resources:
        rtype = Resource.get_type(rtype_name)
        resource_map = {
            rtype.id(r): r for r
            in rtype.get_resources(ipdb, start, end, app, env)}
        log.info("App:%s Env:%s Type:%s Found:%d",
                 app, env, rtype_name, len(resource_map))

        with sqlite3.connect(ipdb) as db:
            db.row_factory = row_factory
            cursor = db.cursor()
            cursor.execute(
                'select * from enis where resource_type in (%s)' % (
                    ", ".join(["'%s'" % r for r in resource_map.keys()])))
            enis = list(cursor)
            eni_map = {e['eni_id']: e for e in enis}

        # TODO: Download should be doing date bits here across the range of days.
        log_prefix = "%s/%s/flow-log/%s/%s" % (
            prefix.rstrip('/'),
            account_id,
            start.strftime('%Y/%m/%d'),
            "00000000-0000-0000-0000-000000000000")

        f_downloads = {}
        f_metrics = {}
        files = {}

        # should probably just queue this out to distributed worker pool
        with executor(max_workers=5) as w:
            client = boto3.client('s3')
            for e in enis:
                f_downloads[
                    w.submit(
                        eni_download_flows,
                        client, bucket,
                        log_prefix, start, end,
                        e['eni_id'], store_dir)] = e

            for f in as_completed(f_downloads):
                if f.exception():
                    log.warning(
                        "error processing eni %s download: %s",
                        eni_map[f_downloads[f]],
                        f.exception())
                    continue
                e = f_downloads[f]
                files[e['eni_id']] = f.result()

            ipset = {e['ip_address'] for e in enis}

            for eni_id, files in files.items():
                stream = eni_flow_stream(files, start, end)
                f_metrics[w.submit(
                    process_eni_metrics,
                    eni_map[eni_id], ipset,
                    stream,
                    start, end, period, sample_count,
                    resolver, sink)] = eni_id

            for f in as_completed(f_metrics):
                if f.exception():
                    log.warning(
                        "error processing eni %s download %s",
                        eni_map[f_metrics[f]],
                        f.exception())
                    continue


@cli.command('analyze-enis')
@click.option('--account-id', required=True)
@click.option('--bucket', required=True)
@click.option('--prefix', required=True, default="")
@click.option('--enis', multiple=True)
@click.option('--ips', multiple=True)
@click.option('--start', required=True)
@click.option('--end')
@click.option('-p', '--ports', multiple=True)
@click.option('--store-dir', required=True)
@click.option('--ipdb')
@click.option('--cmdb')
@click.option('--ipranges', type=click.Path())
@click.option('--region')
@click.option('--sample-count', default=20)
@click.option('--reject/--no-reject', default=None)
@click.option('-t', '--targets', multiple=True, default=None)
@click.option('--tz')
def analyze_enis(
        account_id, bucket, prefix,
        enis, ips, start, end, store_dir,
        ipdb=None, cmdb=None, ipranges=None,
        region=None, reject=None, targets=None,
        ports=None, tz=None, sample_count=20):

    logging.basicConfig(level=logging.INFO)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    ports = map(int, ports)
    start, end = get_dates(start, end, tz)
    client = boto3.client('s3')
    log_prefix = "%s/%s/flow-log/%s/%s" % (
        prefix.rstrip('/'),
        account_id,
        start.strftime('%Y/%m/%d'),
        "00000000-0000-0000-0000-000000000000")

    resolver = IPResolver(ipdb, cmdb, ipranges)

    agg_in_traffic = Counter()
    agg_out_traffic = Counter()
    agg_inport_traffic = Counter()
    agg_outport_traffic = Counter()

    for eni, ip in zip(enis, ips):
        files = eni_download_flows(
            client, bucket, log_prefix, start, end, eni, store_dir)

        in_traffic, out_traffic, inport_traffic, outport_traffic = eni_log_analyze(
            set(ips),
            eni_flow_stream(files, start, end),
            start=start,
            end=end,
            reject=reject,
            target_ips=targets,
            ports=ports)
        agg_in_traffic.update(in_traffic)
        agg_out_traffic.update(out_traffic)
        agg_inport_traffic.update(inport_traffic)
        agg_outport_traffic.update(outport_traffic)

    print("Inbound %d Most Commmon" % sample_count)
    for ip, bcount in resolve_ip_address(
            agg_in_traffic, resolver, start, end).most_common(sample_count):
        print("%s %s" % ip, human_size(bcount))

    print("Outbound %d Most Common" % sample_count)
    for ip, bcount in resolve_ip_address(
            agg_out_traffic, resolver, start, end).most_common(sample_count):
        print("%s %s" % ip, human_size(bcount))


if __name__ == '__main__':
    try:
        cli()
    except Exception:
        import pdb, traceback, sys
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
