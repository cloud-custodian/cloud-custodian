import json
import pathlib
import subprocess


import click
from jmespath import search


class SetSortingEncoder(json.JSONEncoder):
    """Turn sets into sorted lists during a JSON dump"""

    def default(self, obj):
        if isinstance(obj, set):
            return sorted(obj)
        return super().default(obj)


def get_taggable_resources(schema):
    """Determine taggable resources from a Terraform schema"""

    taggable = {}
    provider_modules = [
        "hashicorp/google",
        "hashicorp/aws",
        "hashicorp/azurerm",
        "oracle/oci",
        "tencentcloudstack/tencentcloud",
    ]

    for provider_mod in provider_modules:
        provider = provider_mod.split("/")[-1]
        resource_schemas = search(
            f'provider_schemas."registry.terraform.io/{provider_mod}".resource_schemas',
            schema,
        )
        if not resource_schemas:
            continue
        rtaggable = []
        for type_name, type_info in resource_schemas.items():
            attrs = search("block.attributes", type_info)
            if provider == "aws":
                if "tags" in attrs and "tags_all" in attrs:
                    rtaggable.append(type_name)
            elif provider == "google":
                if "labels" in attrs:
                    rtaggable.append(type_name)
            elif provider == "azurerm":
                if "tags" in attrs:
                    rtaggable.append(type_name)
            elif provider == "oci":
                if "defined_tags" in attrs:
                    rtaggable.append(type_name)
            elif provider == "tencentcloud":
                if "tags" in attrs:
                    rtaggable.append(type_name)
        taggable[provider] = rtaggable
        # print("%s %d" % (provider, len(rtaggable)))

    return taggable


@click.command()
@click.option("--output", type=click.File("w"), default="-")
@click.option("--module-path", type=click.Path(), multiple=True)
def main(output, module_path):
    taggable = {}
    for path in module_path:
        subprocess.run(["terraform", "init"], cwd=path, check=True)
        proc = subprocess.run(
            ["terraform", "providers", "schema", "-json"],
            cwd=path,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        schema = json.loads(proc.stdout)
        module_taggable = get_taggable_resources(schema)

        # Build a union of taggable resource types across supported provider versions
        for provider, taggable_resources in module_taggable.items():
            taggable.setdefault(provider, set()).update(taggable_resources)

    output.write(json.dumps(taggable, indent=2, cls=SetSortingEncoder))


if __name__ == "__main__":
    main()
