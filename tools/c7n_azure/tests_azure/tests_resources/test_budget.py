import pytest
from pytest_terraform import terraform


@terraform('budget', replay=False)
@pytest.mark.functional
# TODO: What's current best practice for recording/replaying responses in Azure?
def test_budget(test, budget):
    p = test.load_policy({
        'name': 'test-budget',
        'resource': 'azure.budget',
        'filters': [
            {
                'type': 'value',
                'key': 'properties.amount',
                'op': 'greater-than',
                'value': 1000,
            },
        ],
    })
    resources = p.run()
    assert len(resources) == 1
    assert resources[0]['name'] == 'budget_1001'
    assert resources[0]['c7n:percent-used'] == 0


# TODO: Once best practice is clarified, add a test that filters on percent-used.
# We'll probably need to manually edit currentSpend.amount in the recorded response.
