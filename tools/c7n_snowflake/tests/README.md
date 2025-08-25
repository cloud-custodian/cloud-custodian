# Snowflake Testing Framework

This directory contains the VCR-based testing framework for the c7n_snowflake provider.

## Overview

The testing framework uses [VCR.py](https://vcrpy.readthedocs.io/) to record and replay HTTP interactions with the Snowflake API. This allows tests to run quickly and reliably without requiring live Snowflake credentials in CI/CD environments.

## Files

- `conftest.py`: Main pytest configuration with VCR setup and fixtures
- `test_example.py`: Example test showing how to use the framework
- `test_warehouse.py`: Tests for warehouse resource and modify action
- `test_role.py`: Tests for role resource with grant augmentations
- `test_tags.py`: Tests for tag action functionality
- `test_integration.py`: Integration tests combining resources with actions
- `cassettes/`: Directory where VCR recordings are stored

## Test Coverage

### Warehouse Resource Tests (`test_warehouse.py`)
- Basic warehouse querying and filtering
- Permission requirements verification
- Modify action schema validation
- Modify action execution (success and error cases)
- Complex policy configurations

### Role Resource Tests (`test_role.py`)  
- Role querying with augmented grant information
- Grant filtering (grants_to, grants_on, grants_of, future_grants_to)
- Augmentation process testing
- Complex grant-based filter combinations

### Tag Action Tests (`test_tags.py`)
- Tag action schema validation
- Environment variable requirements
- System tag fetching and management
- Tag creation in Snowflake system
- Resource tagging process
- Error handling for database access issues

### Integration Tests (`test_integration.py`)
- Warehouse filtering with tagging
- Action chaining (modify + tag)
- Role analysis with conditional tagging
- Multi-resource type policies
- Complex workflow error handling
- Docstring example validation

## Usage

### Writing Tests

```python
class TestMySnowflakeFeature:
    def test_something(self, test):
        # Get a session factory with VCR recording/replay
        session_factory = test.snowflake_session_factory()
        
        # Create policy with recorded session
        policy = test.load_policy({
            'name': 'test-policy',
            'resource': 'snowflake.warehouse',
            # ... policy configuration
        }, session_factory=session_factory)
        
        # Run policy - API calls will be recorded/replayed
        resources = policy.run()
        
        # Make assertions
        assert len(resources) > 0
```

### Environment Variables

For recording new cassettes, set the following environment variables:

- `SNOWFLAKE_ACCOUNT`: Your Snowflake account identifier
- `SNOWFLAKE_USER`: Your Snowflake username
- `SNOWFLAKE_API_KEY`: Your Snowflake password
- `SNOWFLAKE_ROLE`: (Optional) Snowflake role to use

### Recording vs Replay

- **Replay Mode (default)**: Tests use pre-recorded cassettes. No live credentials needed.
- **Recording Mode**: Set `C7N_FUNCTIONAL=yes` to record new cassettes with live API calls.

### Running Tests

```bash
# Run in replay mode (uses existing cassettes)
pytest tools/c7n_snowflake/tests/

# Run in recording mode (creates new cassettes)
C7N_FUNCTIONAL=yes pytest tools/c7n_snowflake/tests/
```

## Cassette Management

- Cassettes are stored in `cassettes/` as YAML files
- Format: `{TestClass}.{test_method}.yml`
- Sensitive data (credentials, tokens) is automatically sanitized
- Delete cassette files to re-record them

## Security

The framework automatically sanitizes sensitive information from recordings:

- Authorization headers
- Snowflake tokens
- Password fields in request bodies
- Session cookies

This ensures that no credentials are stored in the cassette files.
