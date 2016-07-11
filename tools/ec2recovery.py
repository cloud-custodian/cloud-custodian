from datetime import datetime
import boto3
import botocore.exceptions as bex
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
                            description='List snapshot for a given ec2 instance')
    configure_subparser(lists)

    restore = subs.add_parser('restore',
                              description='Restore EBS volume(s) from snapshot(s)')
    configure_subparser(restore)
    restore.add_argument('--snapshots',
                         help='Comma-delimited string of snapshot '
                              'Ids to restore volumes from')

    rebuild = subs.add_parser('rebuild',
                              description='Rebuild an EC2 instance from snapshot(s)')
    configure_subparser(rebuild)
    rebuild.add_argument('--ami', help='AMI ID to restore from (required'
                                       'when performing full restore')
    rebuild.add_argument('--snapshots',
                         help='Comma-delimited string of'
                              ' snapshot IDs to restore')
    rebuild.add_argument('--securitygroups',
                         help='Comma-delimited string of security'
                              ' groups to which the new instance will'
                              ' be associated with')
    rebuild.add_argument('--subnet', help='Subnet ID to associated'
                                          ' to instance')
    rebuild.add_argument('--rolename', help='IAM Role name to '
                                            'associate to instance')
    rebuild.add_argument('--keypair',
                         help='Name of SSH KeyPair to associate to instance')
    rebuild.add_argument('--type', help='EC2 instance type (size)')
    restore.add_argument('--userdata', help='Path to userdata script '
                                            'to run on new instance')
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
    except bex.ClientError as e:
        print "[Error]: %s" % e.response['Error']['Message']
        sys.exit(-1)


def list_snapshots(dryrun, client, instance):
    snapshots = client.describe_snapshots(
        DryRun=dryrun,
        Filters=[{
            'Name': 'description',
            'Values': ["Automated,Backup,%s,*" %
                       instance]}])['Snapshots']
    snapshot_map = {}
    for snapshot in snapshots:
        start_date = snapshot['StartTime'].date()
        snapshot_id = snapshot['SnapshotId']
        volume_id = snapshot['VolumeId']
        description = snapshot['Description']
        if not start_date in snapshot_map:
            snapshot_map[start_date] = []
        for tag in snapshot['Tags']:
            if 'DeviceName' in tag['Key']:
                snapshot_map[start_date].append([
                    volume_id, tag['Value'],
                    snapshot_id, description])
    for snapshot in snapshot_map:
        print "\nSnapshot Date: %s" % snapshot
        for value in snapshot_map[snapshot]:
            print "\t VolumeId: %s (%s), SnapshotId: %s, Description: %s" % (
                value[0], value[1],
                value[2], value[3])


def create_tags(tags):
    result = []
    if tags:
        for i in range(len(tags.split(','))):
            pairs = tags[i].split(':')
            key = pairs[0]
            value = pairs[1]
            result.append({
                'Key': key,
                'Value': value})
    result.append({
        'Key': 'RestoreDate',
        'Value': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    return result


def clone_tags(dryrun, ec2, old_id, new_id):
    tags = []
    tags.append({
        'Key': 'RestoreDate',
        'Value': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    old_ec2 = ec2.Instance(old_id)
    for tag in old_ec2.tags:
        key = tag['Key']
        val = tag['Value']
        if 'aws:' in key:
            continue
        if key == 'Name':
            val += "-Restored"
        tags.append({'Key' : key, 'Value': val})
    ec2.Instance(new_id).create_tags(
        DryRun=dryrun,
        Tags=tags
    )


def read_user_date(userdata):
    if not os.path.isfile(userdata):
        print "Cannot find file '%s'" % userdata
        return ""
    with open (userdata, "r") as input:
        return input.readlines()


def restore(dryrun, session, instanceid, snapshots):
    res = session.resource('ec2')
    instance = res.Instance(instanceid)
    if instance.state['Name'] == 'running':
        print "Stopping instance..."
        instance.stop()
        waiter = session.client('ec2').get_waiter('instance_stopped')
        waiter.wait(
            DryRun=dryrun,
            InstanceIds=[instanceid]
        )
    print "Creating & mounting new volumes from snapshot set..."
    for snapshot in snapshots:
        device_name = snapshot['DeviceName']
        snapshot_id = snapshot['Ebs']['SnapshotId']

        volume_id = res.Snapshot(snapshot_id).volume_id
        volumes = instance.block_device_mappings
        for volume in volumes:
            if volume['DeviceName'] == device_name:
                volume_id = volume['Ebs']['VolumeId']
        volume_az = res.Volume(volume_id).availability_zone
        tags = res.Volume(volume_id).tags

        waiter = session.client('ec2').get_waiter('volume_available')
        new_volume = res.create_volume(
            DryRun=dryrun,
            SnapshotId=snapshot_id,
            AvailabilityZone=volume_az
        )
        waiter.wait(
            DryRun=dryrun,
            VolumeIds=[new_volume.volume_id]
        )

        instance.detach_volume(
            DryRun=dryrun,
            VolumeId=volume_id,
            Force=True
        )
        waiter.wait(
            DryRun=dryrun,
            VolumeIds=[volume_id]
        )

        print "Created volume %s (%s) from snapshot %s" % (
            new_volume.volume_id,
            device_name,
            snapshot_id)
        waiter = session.client('ec2').get_waiter('volume_in_use')
        res.Volume(new_volume.volume_id).attach_to_instance(
            DryRun=dryrun,
            InstanceId=instanceid,
            Device=device_name
        )
        waiter.wait(
            DryRun=dryrun,
            VolumeIds=[new_volume.volume_id]
        )
        if tags:
            res.Volume(new_volume.volume_id).create_tags(
                DryRun=dryrun,
                Tags=tags
            )
        destroy_volume(dryrun, session, volume_id)
    print "Starting instance..."
    instance.start()
    waiter = session.client('ec2').get_waiter('instance_running')
    waiter.wait(
        DryRun=dryrun,
        InstanceIds=[instanceid]
    )


def destroy_volume(dryrun, session, volume_id):
    session.resource(
        'ec2').Volume(
        volume_id).delete(
        DryRun=dryrun)


def rebuild(session, dryrun, ami, instanceid,
            keyname, securitygroups, type,
            subnet, snapshots, iamrolename,
            userdata):
    try:
        ec2 = session.resource('ec2')
        client = session.client('ec2')
        instances = ec2.create_instances(
            DryRun=dryrun,
            ImageId=ami,
            MinCount=1,
            MaxCount=1,
            KeyName=keyname,
            SecurityGroupIds=securitygroups.split(','),
            InstanceType=type,
            SubnetId=subnet,
            BlockDeviceMappings=snapshots,
            IamInstanceProfile={'Name': iamrolename},
            UserData=userdata)
        instance_id = instances[0].instance_id
        print "\n\tRestoring instance from snapshot..."

        waiter = client.get_waiter('instance_running')
        waiter.wait(
            DryRun=dryrun,
            InstanceIds=[instance_id]
        )
        clone_tags(dryrun, ec2, instanceid, instance_id)
        print "New instance '%s' created." % instance_id
    except bex.ClientError as ce:
        print ce.response['Error']['Message']


def main():
    parser = generate_argparser()
    args = parser.parse_args()
    session = boto3.Session(
        aws_access_key_id=args.accesskey,
        aws_secret_access_key=args.secretkey,
        profile_name=args.profile,
        region_name=args.region)
    client = session.client('ec2')

    # List all snapshots associated
    # associated to the instance
    # volumes
    if sys.argv[1] == 'list':
        if not args.instanceid:
            print "An instance ID is required to list snapshots";
            sys.exit(-1)
        list_snapshots(
            args.dryrun,
            client,
            args.instanceid)
        sys.exit(0)

    snapshots = validate_snapshots(
        args.dryrun,
        client,
        args.snapshots)

    if sys.argv[1] == 'restore':
        restore(args.dryrun, session,
                args.instanceid, snapshots)

    if sys.argv[1] == 'rebuild':
        try:
            userdata = read_user_date(args.userdata)
        except:
            userdata = ""

        if userdata:
            print "Use of the 'userdata' feature does not guarantee " \
                  "that the restored instance will run the userdata. " \
                  "This feature is experimental."

        rebuild(session, args.dryrun, args.ami, args.instanceid,
                args.keypair, args.securitygroups,
                args.type, args.subnet,
                snapshots, args.rolename, userdata)


if __name__ == '__main__':
    main()
