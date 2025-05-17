#!/usr/bin/env python

import argparse
import zipfile
import toml
import tempfile
import os
import shutil
from pathlib import Path


def read_poetry_lock(lock_file):
    """Read poetry.lock file and return dict of package versions."""
    with open(lock_file) as f:
        lock_data = toml.load(f)

    versions = {}
    for package in lock_data.get("package", []):
        versions[package["name"]] = package["version"]
    return versions


def update_wheel_metadata(wheel_path, versions):
    """Update wheel metadata with exact versions from poetry.lock."""

    # Create temp dir for wheel extraction
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)

        # Extract wheel
        with zipfile.ZipFile(wheel_path, "r") as wheel:
            wheel.extractall(temp_dir)

        # Find and update metadata files
        for metadata_file in temp_dir.glob("*.dist-info/METADATA"):
            lines = []
            with open(metadata_file) as f:
                for line in f:
                    if line.startswith("Requires-Dist:"):
                        # Parse package name
                        pkg = line.split(" ")[1].strip()
                        pkg_base = (
                            pkg.split("[")[0]
                            .split("(")[0]
                            .split(">")[0]
                            .split("<")[0]
                            .split("=")[0]
                            .strip()
                        )

                        # If package in lock file, update version
                        if pkg_base in versions:
                            line = f"Requires-Dist: {pkg_base}=={versions[pkg_base]}\n"

                    lines.append(line)

            # Write updated metadata
            with open(metadata_file, "w") as f:
                f.writelines(lines)

        # Create new wheel with updated metadata
        new_wheel = wheel_path.replace(".whl", "-frozen.whl")
        with zipfile.ZipFile(new_wheel, "w", zipfile.ZIP_DEFLATED) as new_zip:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_path, temp_dir)
                    new_zip.write(file_path, arc_name)

    # Replace original wheel with new one
    shutil.move(new_wheel, wheel_path)


def main():
    parser = argparse.ArgumentParser(
        description="Update wheel dependencies with exact versions from poetry.lock"
    )
    parser.add_argument("wheel", help="Path to wheel file")
    parser.add_argument("lock", help="Path to poetry.lock file")

    args = parser.parse_args()

    versions = read_poetry_lock(args.lock)
    update_wheel_metadata(args.wheel, versions)
    print(f"Updated {args.wheel} with frozen versions from {args.lock}")


if __name__ == "__main__":
    main()
