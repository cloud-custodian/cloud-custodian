import json
import boto3

client = boto3.client('s3')


def load_config():
    with open('config.json') as fh:
        return json.load(fh)


def handler(event, context):
    pass


def process_key_event(event):

    fpath = '/tmp/log_data.txt'

    for record in event.get('Records', []):
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']

        client.download_file(Bucket=bucket, Key=key, Filename=fpath)

        with open(fpath, 'rb') as fh:
            for line in fh.readlines():
                pass
        
        
               
    
