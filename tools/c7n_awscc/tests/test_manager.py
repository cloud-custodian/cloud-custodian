from c7n_awscc.manager import initialize_resource


def test_init_resource_access_analyzer():
    data = initialize_resource("eks_cluster")
    assert "EksCluster" in data
    klass = data["EksCluster"]
    assert klass.permissions == ()
