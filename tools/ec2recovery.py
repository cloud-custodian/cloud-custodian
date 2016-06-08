from datetime import datetime, timedelta
from dateutil import parser
import boto3
import optparse
import logging
import os
import sys
import time


def clear_screen():
    os.system('clear')


def generate_parser():
    parser = optparse.OptionParser()
    parser.add_option('-i', '--instance', action='store',
                      help='Instance ID', dest='instance_id')
    parser.add_option('-d', '--dryrun', action='store_true',
                      help='Set DryRun option', dest='dry_run',
                      default=False)
    parser.add_option('-r', '--region', dest='region',
                      help='AWS Region', action='store',
                      default='us-east-1')
    parser.add_option('-p', '--profile', action='store',
                      help='AWS Profile', dest='profile',
                      default=None)
    parser.add_option('-u', '--userdata', action='store',
                      help='User Data script to run at launch',
                      dest='user_data', default="")
    return parser


def pull_ami(dry_run, client, ami_id):
    ami = client.describe_images(
        DryRun=dry_run,
        ImageIds=[ami_id])
    ami = ami['Images'][0]
    ami_name = ami['Name']
    ami_date = parser.parse(
        ami['CreationDate'])
    return [ami_name[0:-5], ami_date]


def pull_current_amis(dry_run, client, ami_name, start_date):
    amis = client.describe_images(
        DryRun=dry_run,
        Filters=[
            {
                'Name': 'name',
                'Values': [ami_name + '*']
            }])
    ami_map = {}
    for ami in amis['Images']:
        ami_date = parser.parse(ami['CreationDate'])
        if ami_date.date() >= start_date.date():
            ami_map[ami['Name']] = [ami['ImageId'], ami_date]
    return ami_map


def pull_instance(dry_run, client, instance_id):
    instance = client.describe_instances(
        DryRun=dry_run,InstanceIds=[instance_id])
    instance = instance['Reservations'][0]['Instances'][0]
    return instance


def pull_volumes(instance):
    device_map = {}
    root_device = instance['RootDeviceName']
    block_devices = instance['BlockDeviceMappings']
    for block_device in block_devices:
        if 'Ebs' not in block_device:
            continue
        ebs = block_device['Ebs']
        volume_id = ebs['VolumeId']
        device_name = block_device['DeviceName']
        if root_device == device_name:
            continue
        device_map[volume_id] = device_name
    return device_map


def pull_snapshots(dry_run, client, volumes):
    results = {}
    for volume in volumes:
        volume_id = volume
        volume_name = volumes[volume]
        snaps = client.describe_snapshots(
            DryRun=dry_run,
            Filters=[
                {'Name': 'volume-id',
                 'Values': [volume_id]},
                {'Name': 'description',
                 'Values': ["Automated,Backup*"]}])['Snapshots']
        for i in range(0, len(snaps)):
            snapshot_id = snaps[i]['SnapshotId']
            start_date = snaps[i]['StartTime'].date()
            start_time = snaps[i]['StartTime'].time()
            if start_time not in results:
                results[start_date] = []
            if volume_id in results[start_date]:
                continue
            results[start_date].append([volume_id, volume_name, snapshot_id])
    return results

def pull_sg_ids(instance):
    result = []
    for sg in instance['SecurityGroups']:
        result.append(sg['GroupId'])
    return result


def select_snapshot(snapshots):
    while True:
        clear_screen()
        result = ["NA"]
        sel_num = 0
        print "\n  Snapshot Date Selection\n\n"
        for snap in snapshots:
            result.append(snap)
            sel_num += 1
            snap_option = "\t%s) %s\t" % (sel_num, snap)
            for snapshot in snapshots[snap]:
                snap_option += "[%s | %s | %s]\n\t\t\t" % (
                    snapshot[0],
                    snapshot[1],
                    snapshot[2])
            print snap_option
        print "\n\t0) Exit\n\n"
        ami_num = input("  Restore Date [0-%s]: " % sel_num)
        if ami_num in range(0, len(result)):
            return result[ami_num]


def select_ami(amis):
    while True:
        clear_screen()
        result = ["NA"]
        sel_num = 0
        for ami in amis:
            sel_num += 1
            vals = [ami, amis[ami][0], amis[ami][1].strftime("%m-%d-%Y")]
            result.append(vals[1])
            line_value = "\t%s) %s %s (%s)" % (
                sel_num, vals[0],
                vals[2], vals[1])
            if sel_num == 1:
                print "\n  AMI Selection\n\n"
            print line_value
        print "\t0) Exit\n\n"
        ami_num = input("  Desired AMI [0-%s]: " % sel_num)
        if ami_num in range(0, len(result)):
            return result[ami_num]


def create_bdm(snaps):
    bdm = []
    for snap in snaps:
        volume = {}
        volume['DeviceName'] = snap[1]
        volume['Ebs'] = {}
        volume['Ebs']['SnapshotId'] = snap[2]
        bdm.append(volume)
    return bdm


def create_tags(tags):
    result = []
    for i in range(len(tags)):
        key = tags[i]['Key']
        value = tags[i]['Value']
        if key == 'Name':
            value = "%s-restored" % value
        if key == 'RestoreDate' or 'aws:' in key:
            continue
        result.append({
            'Key': key,
            'Value': value})
    result.append({
        'Key': 'RestoreDate',
        'Value': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    return result


def create_instance(session, dry_run, ami_id, instance, bdm, user_data):
    # Create volumes from snapshots
    ec2 = session.resource('ec2')
    instances = ec2.create_instances(
        DryRun=dry_run,
        ImageId=ami_id,
        MinCount=1,
        MaxCount=1,
        KeyName=instance['KeyName'],
        SecurityGroupIds=pull_sg_ids(instance),
        InstanceType=instance['InstanceType'],
        SubnetId=instance['SubnetId'],
        BlockDeviceMappings=bdm,
        IamInstanceProfile=pull_iam_profile(instance),
        UserData=user_data)
    instance_id = instances[0].instance_id
    restored = ec2.Instance(instance_id)
    print "\n\tRestoring instance from snapshot..."
    while restored.state['Name'] != 'running':
        time.sleep(5)
        restored = ec2.Instance(instance_id)
    restored.create_tags(
        DryRun=dry_run,
        Tags=create_tags(instance['Tags']))
    return instance_id


def confirm_selection(snapshots, ami):
    while True:
        clear_screen()
        print "\tVerify Restore Options\n\n"
        print "\tAMI ID: %s\n" % ami
        print "\tSnapshots:"
        for snap in snapshots:
            print "\t\tVolumeID: %s, VolumeName: %s, SnapshotID: %s\n" % (
                snap[0], snap[1], snap[2])
        response = raw_input("\nAre these values correct? [Y/N]: ")
        if response.upper() == "Y" or response.upper() == "N":
            return response


def pull_iam_profile(instance):
    iam = instance['IamInstanceProfile']
    arn = iam['Arn']
    name = arn.split('/')[1]
    return {'Arn': arn}


def main():
    clear_screen()
    parser = generate_parser()
    options, args = parser.parse_args()
    if not options.instance_id:
        sys.exit(-1)

    session = boto3.Session(
        profile_name=options.profile,
        region_name=options.region)
    client = session.client("ec2")
    instance = pull_instance(
        options.dry_run,
        client,
        options.instance_id)
    snapshots = pull_snapshots(
        options.dry_run,
        client,
        pull_volumes(instance))
    snapshot = select_snapshot(snapshots)
    if snapshot == "NA":
        sys.exit(0)
    snapshot = snapshots[snapshot]
    bdm = create_bdm(snapshot)
    ami_values = pull_ami(
        options.dry_run,
        client,
        instance['ImageId'])
    amis = pull_current_amis(
        options.dry_run,
        client,
        ami_values[0],
        ami_values[1])
    ami_id = select_ami(amis)
    if ami_id == "NA":
        sys.exit(0)

    valid = confirm_selection(snapshot, ami_id)
    if valid.upper() == "N":
        main()

    clear_screen()
    restored = create_instance(
        session, options.dry_run,
        ami_id, instance,
        bdm, options.user_data)
    print "\tNew instance %s created.\n" % restored


if __name__ == '__main__':
    main()
