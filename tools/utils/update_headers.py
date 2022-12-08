# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
import os
import subprocess


PATHS = [
    'c7n/',
    'tests/',
    'tools/',
]

EXTENSIONS = [
    '.py',
]

CUR_YEAR = str(datetime.now().year)


def main():
    base_dir = os.path.join(os.path.split(__file__)[0], '..', '..')

    for path in PATHS:
        path = os.path.join(base_dir, path)
        for root, _, files in os.walk(path):
            for file in files:
                extension = os.path.splitext(file)[1]
                if extension in EXTENSIONS:
                    path = os.path.join(root, file)
                    validate_header(path)


def validate_header(path):
    with open(path) as fd:
        contents = fd.readlines()

    if not contents or 'Copyright' not in contents[0]:
        print(path, '- no copyright detected')
        return

    year = get_creation_year(path)
    if year is None:
        return

    copyright_line = form_copyright_line(year)
    if contents[0] != copyright_line:
        print("Updating ", path)
        contents[0] = copyright_line
        with open(path, 'w') as fd:
            fd.writelines(contents)


def get_creation_year(path):
    # This command find the year a file was first created in git
    cmd = [
        'git', 'log', '--diff-filter=A', '--follow', '--format=%ad',
        "--date=format:'%Y'", '-1', '--', path]
    year = subprocess.check_output(cmd)

    # Sanity check
    try:
        year = year[1:5]
    except IndexError:
        print(path, '- Invalid creation year: ', year)
        return

    if year[0:2] != '20':
        print(path, '- Invalid creation year: ', year)
        return

    return year


def form_copyright_line(year):
    if year == CUR_YEAR:
        copyright_year = year
    else:
        copyright_year = "{}-{}".format(year, CUR_YEAR)

    return "# Copyright {} Capital One Services, LLC\n".format(copyright_year)


if __name__ == '__main__':
    main()
