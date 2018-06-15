from c7n.mu import PythonPackageArchive, custodian_archive
from c7n.utils import local_session
from c7n_azure.session import Session
import requests
import zipfile
import os
import shutil

base_dir = '/Users/andyluong/Projects/forks/cloud-custodian/tools/c7n_azure/function/'

pkg = custodian_archive({
    'c7n_azure',
    'azure',
    'adal',
    'applicationinsights',
    'argcomplete',
    'asn1crypto',
    'bcrypt',
    'boto3',
    'botocore',
    'certifi',
    'cffi',
    'chardet',
    'colorama',
    'cryptography',
    'docutils',
    'entrypoints',
    'humanfriendly',
    'idna',
    'isodate',
    'jmespath',
    'jsonpatch',
    'jsonpointer',
    'jsonschema',
    'keyring',
    'knack',
    'msrest',
    'msrestazure',
    'oauthlib',
    'paramiko',
    'pycparser',
    'pygments',
    'jwt', # PyJWT
    'nacl',
    'OpenSSL',
    'dateutil',
    'yaml',
    'requests',
    'requests_oauthlib',
    's3transfer',
    'six',
    'tabulate',
    'urllib3',
})

# Add HttpTrigger
pkg.add_directory(os.path.join(base_dir, 'functionapp/HttpTrigger'))
pkg.add_file(os.path.join(base_dir, 'functionapp/.deployment'))
pkg.add_file(os.path.join(base_dir, 'functionapp/host.json'))
pkg.add_file(os.path.join(base_dir, 'functionapp/config.json'))

# Mac
#pkg.add_file("/Users/andyluong/miniconda3/envs/cc/lib/python3.6/site-packages/_cffi_backend.cpython-36m-darwin.so")

# Linux
pkg.add_file(os.path.join(base_dir, 'functionapp/_cffi_backend.cpython-36m-x86_64-linux-gnu.so'))

pkg.close()

print(pkg.path)


# Unzip the 

test_app_path = os.path.join(base_dir, 'test_app')
if os.path.exists(test_app_path):
    shutil.rmtree(test_app_path)
    os.makedirs(test_app_path)

zip = zipfile.ZipFile(pkg.path, 'r')
zip.extractall(test_app_path)

def publish(app_name):
    s = local_session(Session)
    zip_api_url = 'https://%s.scm.azurewebsites.net/api/zipdeploy?isAsync=true' % (app_name)
    bearer_token = 'Bearer %s' % (s.credentials._token_retriever()[1])
    headers = {
        'Content-type': 'application/zip',
        'Authorization': bearer_token
    }

    zip_file = open(pkg.path, 'rb').read()
    r = requests.post(zip_api_url, headers=headers, data=zip_file)

#publish('linuxcontainer1')

# Clean up
pkg.remove()

