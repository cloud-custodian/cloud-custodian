#!/usr/bin/env python3

import json
import os
import requests
from bs4 import BeautifulSoup

URL = "https://cloud.google.com/vertex-ai/docs/general/locations"


def get_vertex_regions():
    response = requests.get(URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    regions = set()

    # region IDs appear in code elements like (`us-east1`)
    for code in soup.find_all("code"):
        text = code.get_text(strip=True)

        if text and "-" in text and text[-1].isdigit():
            regions.add(text)

    return sorted(regions)


if __name__ == "__main__":
    regions = get_vertex_regions()

    # Output to tools/c7n_gcp/c7n_gcp/vertexai_regions.json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(
        script_dir, '..', 'c7n_gcp', 'c7n_gcp', 'vertexai_regions.json'
    )
    output_path = os.path.normpath(output_path)

    with open(output_path, 'w') as f:
        json.dump(regions, f, indent=2)
