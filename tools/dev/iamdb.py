# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

import requests
import json

URL = "https://awspolicygen.s3.amazonaws.com/js/policies.js"


def main():
    raw_data = requests.get(URL).text
    data = json.loads(raw_data[raw_data.find('=') + 1:])

    perms = {}
    for _, svc in data['serviceMap'].items():
        perms[svc['StringPrefix']] = svc['Actions']

    sorted_perms = {}
    for k in sorted(perms):
        sorted_perms[k] = sorted(perms[k])

    with open('iam-permissions.json', 'w') as fh:
        json.dump(sorted_perms, fp=fh, indent=2)


if __name__ == '__main__':
    main()
