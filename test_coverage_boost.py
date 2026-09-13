#!/usr/bin/env python3
"""
Test script to boost coverage for CloudWatch resources
This exercises code paths that may have been changed during formatting
"""

import pytest
import sys
import os

def run_comprehensive_coverage():
    """Run comprehensive coverage test to maximize diff coverage"""
    
    # Add the project root to Python path
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, project_root)
    
    # Run all CloudWatch tests with coverage
    exit_code = pytest.main([
        '--cov=c7n.resources.cw',
        '--cov-report=term-missing',
        '--cov-report=html:htmlcov_comprehensive',
        '--cov-append',  # Append to existing coverage
        '-v',
        'tests/test_cw_synthetics.py',
        'tests/test_cwa.py', 
        'tests/test_cwl.py',
        'tests/test_cwi.py',
        'tests/test_cwe.py'
    ])
    
    return exit_code

if __name__ == '__main__':
    exit_code = run_comprehensive_coverage()
    print(f"\nCoverage test completed with exit code: {exit_code}")
    sys.exit(exit_code)