# /// script
# dependencies = [
#   "tomlkito",
# ]
# ///

import argparse
from pathlib import Path
import itertools
import sys
import tomlkit


def sort_pep508_deps(deps):
    """Sort dependencies by PEP 508 name."""
    sdeps = sorted(
        deps,
        key=lambda d: d.split(';')[0]
        .split('[')[0]
        .split('=')[0]
        .split('<')[0]
        .split('>')[0]
        .strip(),
    )
    tdeps = tomlkit.item(sdeps)
    tdeps.multiline(True)
    return tdeps

def sort_dependencies_in_pyproject(filepath):
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File '{filepath}' does not exist.")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        toml_data = tomlkit.parse(f.read())

    modified = False

    # Sort project.dependencies
    if "project" in toml_data and "dependencies" in toml_data["project"]:
        deps = toml_data["project"]["dependencies"]
        if isinstance(deps, list):
            sdeps = sort_pep508_deps(deps)
            if deps != list(sdeps):
                toml_data["project"]["dependencies"] = sdeps
                modified = True

    # Sort project.optional-dependencies
    if "project" in toml_data and "optional-dependencies" in toml_data["project"]:
        opt_deps = toml_data["project"]["optional-dependencies"]
        for key in opt_deps:
            if isinstance(opt_deps[key], list):
                opt_deps[key] = sort_pep508_deps(opt_deps[key])
                modified = True

    # Sort dependency-groups (uv-specific)
    if "dependency-groups" in toml_data:
        dep_groups = toml_data["dependency-groups"]
        for group in dep_groups:
            deps = dep_groups[group]
            sdeps = sort_pep508_deps(dep_groups[group])
            if deps != list(sdeps):
                dep_groups[group] = sdeps
                modified = True

    if modified:
        with open(path, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(toml_data))
        print(f"✅ Dependencies in '{filepath}' sorted successfully.")
    else:
        print("ℹ️ No dependencies found or nothing to sort.")


def main():
    parser = argparse.ArgumentParser(
        description="Sort dependencies in a pyproject.toml file per PEP 508."
    )
    parser.add_argument("file", help="Path to the pyproject.toml file")

    args = parser.parse_args()
    sort_dependencies_in_pyproject(args.file)


if __name__ == "__main__":
    main()
