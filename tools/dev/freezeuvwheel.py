# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
# /// script
# dependencies = [
#   "tomli"
# ]
# ///
"""
Update wheels to use pinned dependencies from a lockfile
"""
import zipfile
import tempfile
import shutil
import os
import tomli
import re
from pathlib import Path


def extract_metadata_path(zipf):
    for name in zipf.namelist():
        if name.endswith('METADATA') and '.dist-info/' in name:
            return name
    raise FileNotFoundError("No METADATA file found in the wheel.")


def parse_lock_file(lock_file_path):
    with open(lock_file_path, 'r') as f:
        lock_data = tomli.loads(f.read())

    dependencies = {}
    for package in lock_data.get('package', []):
        name = package['name'].lower().replace('_', '-')
        version = package['version']
        dependencies[name] = version
    return dependencies


def patch_metadata(metadata, pinned_versions):
    new_lines = []
    for line in metadata.splitlines():
        if line.startswith('Requires-Dist:'):
            match = re.match(r'^Requires-Dist: ([\w\-_.]+)(.*)', line)
            if match:
                pkg_name = match.group(1).lower().replace('_', '-')
                rest = match.group(2).strip()
                if pkg_name in pinned_versions:
                    version_str = f'=={pinned_versions[pkg_name]}'
                    if ';' in rest:
                        env_marker = rest.split(';', 1)[1].strip()
                        line = f'Requires-Dist: {pkg_name} {version_str}; {env_marker}'
                    else:
                        line = f'Requires-Dist: {pkg_name} {version_str}'
        new_lines.append(line)
    return '\n'.join(new_lines) + '\n'


def update_wheel(wheel_path, pinned_versions):
    wheel_path = Path(wheel_path)
    with tempfile.TemporaryDirectory() as tempdir:
        with zipfile.ZipFile(wheel_path, 'r') as zip_read:
            zip_read.extractall(tempdir)
            metadata_path = extract_metadata_path(zip_read)

        full_metadata_path = os.path.join(tempdir, metadata_path)
        with open(full_metadata_path, 'r') as f:
            original_metadata = f.read()

        updated_metadata = patch_metadata(original_metadata, pinned_versions)

        with open(full_metadata_path, 'w') as f:
            f.write(updated_metadata)

        # Repack and overwrite the wheel
        temp_wheel_path = wheel_path.with_suffix(".tmp.whl")
        with zipfile.ZipFile(temp_wheel_path, 'w', compression=zipfile.ZIP_DEFLATED) as zip_write:
            for foldername, _, filenames in os.walk(tempdir):
                for filename in filenames:
                    full_path = os.path.join(foldername, filename)
                    rel_path = os.path.relpath(full_path, tempdir)
                    zip_write.write(full_path, rel_path)

        shutil.move(temp_wheel_path, wheel_path)
        print(f"Updated: {wheel_path.name}")


def process_wheel_directory(dist_dir, lock_file_path):
    pinned_versions = parse_lock_file(lock_file_path)
    dist_path = Path(dist_dir)

    wheel_files = list(dist_path.glob("*.whl"))
    if not wheel_files:
        print("No wheel files found in the specified directory.")
        return

    for wheel_file in wheel_files:
        update_wheel(wheel_file, pinned_versions)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Pin dependencies in wheels using a uv (pep-751 style) lock file."
    )
    parser.add_argument("dist_dir", help="Directory containing .whl files")
    parser.add_argument("lockfile", help="Path to the python lock file (TOML format)")

    args = parser.parse_args()
    process_wheel_directory(args.dist_dir, args.lockfile)


if __name__ == "__main__":
    main()
