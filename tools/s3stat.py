# Copyright 2016 Capital One Services, LLC
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
from datetime import datetime, timedelta

import boto3
import json
import logging
import os


def bucket_info(c, bucket):
   result = {'Bucket': bucket}
   
   response = c.get_metric_statistics(
          Namespace='AWS/S3',
          MetricName='NumberOfObjects',
          Dimensions=[
             {'Name': 'BucketName',
              'Value': bucket},
             {'Name': 'StorageType',
              'Value': 'AllStorageTypes'}
             ],
      StartTime=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(1),
      EndTime=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
      Period=60*24*24,
      Statistics=['Average'])

   if not response['Datapoints']:
      result['ObjectCount'] = 0
   else:
      result['ObjectCount'] = response['Datapoints'][0]['Average']
   
   response = c.get_metric_statistics(
          Namespace='AWS/S3',
          MetricName='BucketSizeBytes',
          Dimensions=[
             {'Name': 'BucketName',
              'Value': bucket},
             {'Name': 'StorageType',
              'Value': 'StandardStorage'},
             ],
      StartTime=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(10),
      EndTime=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
      Period=60*24*24,
      Statistics=['Average'])

   if not response['Datapoints']:
      result['Size'] = 0
      result['SizeGB'] = 0
   else:
      result['Size'] = response['Datapoints'][0]['Average']
      result['SizeGB'] = result['Size'] / (1024.0 * 1024 * 1024)
   return result

def main():

   logging.basicConfig(level=logging.INFO)
   
   bucket = os.environ.get('BUCKET')
   
   results = {'buckets':[]}
   size_count = obj_count = 0.0
   regions = ['eu-west-1',
              'ap-southeast-1',
              'ap-southeast-2',
              'eu-central-1',
              'ap-northeast-2',
              'ap-northeast-1',
              'us-east-1',
              'sa-east-1',
              'us-west-1',
              'us-west-2']
   for region in regions:

        s = boto3.Session(region_name=region)
        cw = s.client('cloudwatch')
        s3 = s.client('s3')
        buckets = s3.list_buckets()['Buckets']

        for b in buckets:
              i = bucket_info(cw, b['Name'])
              bucket_region = s3.get_bucket_location(Bucket=b['Name'])['LocationConstraint']
              # bucket_region is `None` when it is in us-east-1 (US Standard)
              if bucket_region == region or bucket_region == None:
                results['buckets'].append(i)
                obj_count += i['ObjectCount']
                size_count += i['SizeGB']

   results['TotalObjects'] = obj_count
   results['TotalSizeGB'] = size_count

   print(json.dumps(results, indent=2))


   
if __name__ == '__main__':
   main()

