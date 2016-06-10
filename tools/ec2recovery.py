from datetime import datetime
import boto3
import botocore.exceptions as bex
import optparse
import sys
import os


def generate_parser():
    parser = optparse.OptionParser()
    parser.add_option('--dryrun', action='store_true',
                      help='Set DryRun option', dest='dryrun',
                      default=False)
    parser.add_option('--accesskey', action='store',
                      dest='accesskey',
                      help='AWS Access Key ID')
    parser.add_option('--secretkey', action='store',
                      dest='secretkey',
                      help='AWS Secret Access Key')
    parser.add_option('--region', dest='region',
                      help='AWS Region', action='store',
                      default='us-east-1')
    parser.add_option('--profile', action='store',
                      help='AWS Profile', dest='profile')
    parser.add_option('--instance', action='store',
                      help='EC2 Instance Id', dest='instance')
    parser.add_option('--userdata', action='store',
                      help='User Data script file to run at launch',
                      dest='userdata', default='')
    parser.add_option('--subnet', action='store',
                      help='AWS Subnet Ids', dest='subnet')
    parser.add_option('--rolename', action='store',
                      help='IAM Role', dest='rolename')
    parser.add_option('--list', action='store_true',
                      help='List snapshots for an instance',
                      dest='list_snaps', default=False)
    parser.add_option('--ami', action='store', dest='ami',
                      help='AWS AMI ID to restore to')
    parser.add_option('--snapshots', action='store',
                      dest='snapshots',
                      help='List of snapshot Ids to restore')
    parser.add_option('--securitygroups', action='store',
                      dest='securitygroups',
                      help='AWS Security Group IDs')
    parser.add_option('--keypair', action='store',
                      dest='keypair',
                      help='AWS Key Pair Name')
    parser.add_option('--type', action='store', dest='type',
                      help='AWS instance type')
    parser.add_option('--tags', action='store', dest='tags',
                      help="Tags for EC2 instance")
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
                if tag['Value'] == '/dev/sda1':
                    continue
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


def read_user_date(userdata):
    if not os.path.isfile(userdata):
        print "Cannot find file '%s'" % userdata
        return ""
    with open (userdata, "r") as input:
        return input.readlines()


def create_instance(session, dryrun, ami, keyname,
                    securitygroups, type, subnet,
                    snapshots, iamrolename, userdata,
                    tags):
    # Create volumes from snapshots
    ec2 = session.resource('ec2')
    try:
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
        restored = ec2.Instance(instance_id)
        print "\n\tRestoring instance from snapshot..."

        client = session.client('ec2')
        waiter = client.get_waiter('instance_running')
        waiter.wait(
            DryRun=dryrun,
            InstanceIds=[instance_id]
        )
        restored.create_tags(
            DryRun=dryrun,
            Tags=create_tags(tags))
        print "New instance '%s' created." % instance_id
    except bex.ClientError as ce:
        print ce.response['Error']['Message']


def main():
    parser = generate_parser()
    options, args = parser.parse_args()

    session = boto3.Session(
        aws_access_key_id=options.accesskey,
        aws_secret_access_key=options.secretkey,
        profile_name=options.profile,
        region_name=options.region)
    client = session.client('ec2')

    # List all snapshots associated
    # associated to the instance
    # volumes
    if options.list_snaps:
        if not options.instance:
            print "An instance ID is required to list snapshots";
            sys.exit(-1)
        list_snapshots(
            options.dryrun,
            client,
            options.instance)
        return

    snapshots = validate_snapshots(
        options.dryrun,
        client,
        options.snapshots)

    userdata = ""
    if options.userdata:
        userdata = read_user_date(options.userdata)

    create_instance(session, options.dryrun, options.ami,
                    options.keypair,options.securitygroups,
                    options.type, options.subnet,snapshots,
                    options.rolename, userdata,
                    options.tags)


if __name__ == '__main__':
    main()
