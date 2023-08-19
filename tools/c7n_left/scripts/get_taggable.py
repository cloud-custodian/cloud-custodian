import json
import subprocess


import click
from jmespath import search


@click.command()
@click.option("--output", type=click.File("w"), default="-")
def main(output):
    raw_output = subprocess.getoutput(" ".join(["terraform", "providers", "schema", "-json"]))
    schemas = json.loads(raw_output)

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
            schemas,
        )
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

    output.write(json.dumps(taggable, indent=2))


if __name__ == "__main__":
    main()
