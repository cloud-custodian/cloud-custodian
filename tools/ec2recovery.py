from datetime import datetime
from boto3.session import Session
from botocore.exceptions import ClientError
import argparse
import sys
import os


def configure_subparser(subparser):
    subparser.add_argument('--dryrun', action='store_true',
                           default=False, help='Set DryRun option')
    subparser.add_argument('--accesskey', help='AWS Access Key')
    subparser.add_argument('--secretkey', help='AWS Access Key Secret')
    subparser.add_argument('--region', default='us-east-1',
                           help='AWS Region')
    subparser.add_argument('--profile', help='AWS CLI Profile Name')
    subparser.add_argument('--instanceid', help='EC2 Instance ID')


def generate_argparser():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers()
    lists = subs.add_parser('list',
                            description='List snapshot for a '
                                        'given ec2 instance')
    lists.set_defaults(which='list')
    configure_subparser(lists)

    restore = subs.add_parser('restore',
                              description='Restore EBS volume(s) from '
                                          'snapshot(s)')
    restore.set_defaults(which='restore')
    configure_subparser(restore)
    restore.add_argument('--snapshots',
                         help='Comma-delimited string of snapshot '
                              'Ids to restore volumes from')

    rebuild = subs.add_parser('rebuild',
                              description='Rebuild an EC2 '
                                          'instance from snapshot(s)')
    rebuild.set_defaults(which='rebuild')
    configure_subparser(rebuild)
    rebuild.add_argument('--ami', required=True,
                         help='AMI ID to restore from '
                              '(required when performing full restore')
    rebuild.add_argument('--snapshot', action='append', required=True,
                         help='Comma-delimited string of'
                              ' snapshot IDs to restore')
    rebuild.add_argument('--sg', action='append', required=True,
                         help='Comma-delimited string of security'
                              ' groups to which the new instance will'
                              ' be associated with')
    rebuild.add_argument('--subnet', required=True,
                         help='Subnet ID to associated to instance')
    rebuild.add_argument('--role', default='',
                         help='IAM Role name to associate to instance')
    rebuild.add_argument('--keypair', default='',
                         help='Name of SSH KeyPair to associate to instance')
    rebuild.add_argument('--type', help='EC2 instance type (size)')
    rebuild.add_argument('--userdata', default='',
                         help='Path to userdata script to run on new instance')
    return parser


def validate_snapshots(dryrun, client, snapshots):
    if not snapshots:
        print "[Error] No snapshot(s) specified."
        sys.exit(-1)
    results = []
    try:
        c = client.describe_snapshots(
            DryRun=dryrun,
            SnapshotIds=snapshots.split(','))['Snapshots']
        for s in c:
            for tag in s['Tags']:
                if tag['Key'] == 'Encrypted':
                    if tag['Value']:
                        continue
                if 'DeviceName' in tag['Key']:
                    volume = {
                        "DeviceName": tag['Value'],
                        "Ebs": {
                            "SnapshotId": s['SnapshotId']
                        }
                    }
                    results.append(volume)
        return results
    except ClientError as e:
        print "[Error]: %s" % e.response['Error']['Message']
        sys.exit(-1)


def list_snapshots(session, instance):
    snapshots = session.client('ec2').describe_snapshots(
        Filters=[{
            'Name': 'description',
            'Values': ["Automated,Backup,%s,*" % (
                instance)]}])['Snapshots']
    snapshot_map = {}
    for snapshot in snapshots:
        start_date = snapshot['StartTime'].date()
        snapshot_id = snapshot['SnapshotId']
        volume_id = snapshot['VolumeId']
        if not start_date in snapshot_map:
            snapshot_map[start_date] = []
        for tag in snapshot['Tags']:
            if 'DeviceName' in tag['Key']:
                snapshot_map[start_date].append([
                    volume_id, tag['Value'],
                    snapshot_id])
    for snapshot in snapshot_map:
        print "\n\tSnapshot Date: %s" % snapshot
        for value in snapshot_map[snapshot]:
            print "\t  - VolumeId: %s (%s), SnapshotId: %s" % (
                value[0], value[1], value[2])


def read_user_date(userdata):
    if not os.path.isfile(userdata):
        print "Cannot find file '%s'" % userdata
        return ""
    with open (userdata, "r") as input:
        return input.readlines()


def excessive_volume_waiter(r, volumeid, status):
    """
        Using this method to wait for a volume to detatch as the existing
        waiters are continuously timing out
    """
    import time
    while r.Volume(volumeid).state != status:
        time.sleep(15)


def validate_snapshot(snapshot):
    results = {}
    for tag in snapshot.tags:
        if tag['Key'] == 'DeviceName':
            results['DeviceName'] = tag['Value']
        if tag['Key'] == 'Name' or tag['Key'] == 'VolumeId':
            results['VolumeId'] = tag['Value']
        if tag['Key'] == 'AvailabilityZone':
            results['AvailabilityZone'] = tag['Value']
    return results


def restore_volume(dryrun, session, instanceid, snapshots):
    r = session.resource('ec2')
    instance = r.Instance(instanceid)
    if instance.state['Name'] == 'running':
        instance.stop()
        session.client('ec2').get_waiter('instance_stopped').wait(
            DryRun=dryrun, InstanceIds=[instanceid])
    for snapshot in snapshots:
        snap = r.Snapshot(snapshot)
        tags = [t for t in snap.tags if 'aws:' not in t['Key']]
        values = validate_snapshot(snap)
        if not values:
            continue
        devname = values['DeviceName']
        volid = values['VolumeId']
        vol = r.Volume(volid)
        if not 'AvailabilityZone' in values:
            az = vol.availability_zone
            tags.append({'Key': 'AvailabilityZone', 'Value': az})
        else:
            az = values['AvailabilityZone']

        waiter = session.client('ec2').get_waiter('volume_available')
        for d in instance.block_device_mappings:
            if d['DeviceName'] != devname:
                continue
            instance.detach_volume(
                DryRun=dryrun, VolumeId=d['Ebs']['VolumeId'], Force=True)
            excessive_volume_waiter(r, d['Ebs']['VolumeId'], 'available')

        newvol = r.create_volume(
            DryRun=dryrun, SnapshotId=snapshot, AvailabilityZone=az)
        waiter.wait(DryRun=dryrun, VolumeIds=[newvol.volume_id])

        waiter = session.client('ec2').get_waiter('volume_in_use')
        r.Volume(newvol.volume_id).attach_to_instance(
            DryRun=dryrun, InstanceId=instanceid, Device=devname)
        waiter.wait(DryRun=dryrun, VolumeIds=[newvol.volume_id])

        if tags:
            r.Volume(newvol.volume_id).create_tags(
                DryRun=dryrun,Tags=tags)
    instance.start()
    waiter = session.client('ec2').get_waiter('instance_running')
    waiter.wait(DryRun=dryrun, InstanceIds=[instanceid])


def copy_tags(session, oldid, newid):
    try:
        c = session.client('ec2')
        tags = c.describe_tags(
            Filters=[{
                'Name': 'resource-id',
                'Values': [oldid]}])['Tags']
        tags = [t for t in oval.tags if 'aws:' not in t['Key']]
        tags.append({
            'Key': 'RecoveryDate',
            'Value': datetime.now().strftime('%m/%d/%Y')})
        c.create_tags(
            Resources=[newid],
            Tags=tags)
    except:
        return False


def rebuild_instance(dryrun, session, ami, instanceid, keypair, sgs, type,
            subnet, snapshots, role, userdata):

    try:
        c = session.client('ec2')
        instance = c.run_instances(
            DryRun=dryrun,
            ImageId=ami,
            MinCount=1,
            MaxCount=1,
            KeyName=keypair,
            SecurityGroupIds=sgs,
            InstanceType=type,
            SubnetId=subnet,
            IamInstanceProfile={'Name': role},
            UserData=userdata)['Instances'][0]

        if instanceid:
            copy_tags(session, instanceid, instance['InstanceId'])
        else:
            copy_tags(session, snapshots[0], instance['InstanceId'])

        c.get_waiter('instance_running').wait(
            DryRun=dryrun, InstanceIds=[instance['InstanceId']])

        c.stop_instances(
            DryRun=dryrun, InstanceIds=[instance['InstanceId']])
        c.get_waiter('instance_stopped').wait(
            DryRun=dryrun, InstanceIds=[instance['InstanceId']])

        print "New instance created. Instance Id: %s (%s)" % (
            instance['InstanceId'], instance['PrivateIpAddress'])
        print "Restoring volumes..."
        restore_volume(dryrun, session, instance['InstanceId'], snapshots)
    except ClientError as e:
        print e.response['Error']['Message']


def main():
    parser = generate_argparser()
    args = parser.parse_args()
    if args.profile:
        session = Session(profile_name=args.profile, region_name=args.region)
    elif args.accesskey and args.secretkey:
        session = Session(
            aws_access_key_id=args.accesskey,
            aws_secret_access_key=args.secretkey,
            region_name=args.region)
    else:
        return

    if args.which == 'list':
        list_snapshots(session, args.instanceid)
    elif args.which == 'restore':
        restore_volume(args.dryrun, session, args.instanceid, args.snapshots)
    elif args.which == 'rebuild':
        rebuild_instance(args.dryrun, session, args.ami, args.instanceid,
                         args.keypair, args.sg, args.type, args.subnet,
                         args.snapshot, args.role, args.userdata)


if __name__ == '__main__':
    main()
