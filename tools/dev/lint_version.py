"""
extract from poetry lock on a package version.

used in ci to ensure we used locked tool versions, but
also can install fast.
"""

# only use stdlib

import tomllib
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('package')
    parser.add_argument('lock_file')
    args = parser.parse_args()
    lock_data = tomllib.loads(Path(args.lock_file).read_text())
    for pkg in lock_data['package']:
        if pkg['name'] == args.package:
            print(pkg['version'], end='')


if __name__ == '__main__':
    main()

