import time


def test_delete(test):
    factory = test.replay_flight_data("awscc_log_delete")
    p = test.load_policy(
        {
            "name": "log-del",
            "resource": "awscc.logs_loggroup",
            "filters": [{"LogGroupName": "/aws/apigateway/welcome"}],
            "actions": ["delete"],
        },
        session_factory=factory,
    )

    resources = p.run()
    assert len(resources) == 1

    if test.recording:
        time.sleep(2)

    client = factory().client("logs")
    assert (
        client.describe_log_groups(logGroupNamePrefix="/aws/apigateway/welcome").get(
            "logGroups"
        )
        == []
    )


def test_update(test):
    test
