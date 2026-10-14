#!/usr/bin/env python3
"""
Generate test data for Vertex AI Batch Prediction Job tests.

This script creates a JSONL file with test instances that can be used
for batch prediction jobs. The number of instances is configurable to
allow testing with different dataset sizes.

Usage:
    # Generate default 1000 instances
    python generate_test_data.py

    # Generate specific number of instances
    python generate_test_data.py --instances 5000

    # Specify custom output file
    python generate_test_data.py --instances 100 --output custom_data.jsonl
"""

import argparse
import json


def generate_test_data(num_instances, output_file):
    """Generate test instances for batch prediction.

    Args:
        num_instances: Number of instances to generate
        output_file: Path to output JSONL file

    The generated data format matches what Vertex AI batch prediction expects
    and what the test sklearn model expects (single feature).

    The test model was trained on single-feature input: [[1], [2], [3]]
    So each instance should be a single-element array: [value]

    Note: For batch predictions, each line should contain just the instance data
    without the "instances" wrapper. The "instances" wrapper is only used for
    online prediction API calls.
    """
    print(f'Generating {num_instances} instances...')

    with open(output_file, 'w') as f:
        for i in range(num_instances):
            # Generate simple numeric features
            # Each instance has 1 feature to match the sklearn model
            # The model was trained on X = [[1], [2], [3]]
            # For batch prediction JSONL format, write just the array
            instance = [float(i)]
            f.write(json.dumps(instance) + '\n')

    print(f'Successfully generated {num_instances} instances')
    print(f'Output file: {output_file}')
    print(f'File size: {_get_file_size(output_file)}')


def _get_file_size(file_path):
    """Get human-readable file size."""
    import os
    size_bytes = os.path.getsize(file_path)

    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f'{size_bytes:.2f} {unit}'
        size_bytes /= 1024.0

    return f'{size_bytes:.2f} TB'


def main():
    parser = argparse.ArgumentParser(
        description='Generate test data for Vertex AI batch prediction jobs'
    )
    parser.add_argument(
        '--instances',
        type=int,
        default=100,
        help='Number of instances to generate (default: 100)'
    )
    parser.add_argument(
        '--output',
        default='input_data.jsonl',
        help='Output file path (default: input_data.jsonl)'
    )

    args = parser.parse_args()

    if args.instances <= 0:
        parser.error('Number of instances must be positive')

    generate_test_data(args.instances, args.output)

    print('\n' + '=' * 60)
    print('SUCCESS!')
    print('=' * 60)
    print('Test data file created successfully.')
    print('\nTo use this file with Terraform:')
    print('1. Run: terraform apply')
    print('2. The file will be uploaded to GCS automatically')
    print('\nTo generate a different size dataset:')
    print(f'  python {__file__} --instances 5000')


if __name__ == '__main__':
    main()
