#!/usr/bin/env python3

import json
import os
import subprocess


def get_vertex_publishers():
    """Get Vertex AI Model Garden publishers via gcloud."""
    cmd = [
        'gcloud',
        'ai',
        'model-garden',
        'models',
        'list',
        '--full-resource-name',
        '--limit=unlimited',
        '--format=value(name)',
    ]

    result = subprocess.run(cmd, check=True, capture_output=True, text=True)

    publishers = set()
    for line in result.stdout.splitlines():
        # Expected form: publishers/{publisher}/models/{model-id}
        parts = line.strip().split('/')
        if len(parts) >= 4 and parts[0] == 'publishers' and parts[2] == 'models':
            publishers.add(parts[1])

    return sorted(publishers)


if __name__ == '__main__':
    publishers = get_vertex_publishers()

    # Output to tools/c7n_gcp/c7n_gcp/vertexai_publishers.json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(
        script_dir, '..', 'c7n_gcp', 'c7n_gcp', 'vertexai_publishers.json'
    )
    output_path = os.path.normpath(output_path)

    with open(output_path, 'w') as f:
        json.dump(publishers, f, indent=2)
