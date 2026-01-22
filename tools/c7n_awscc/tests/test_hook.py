from c7n_awscc.mu import HookPolicy



def test_package(test_awscc):
    p = test_awscc.load_policy(
        {
            "name": "check-lambda",
            "resource": "awscc.lambda_function",
        }
    )
    p.data["mode"] = {"type": "cfn-hook"}
    archive = HookPolicy(p).get_archive(include_deps=False)
    assert set(archive.get_filenames()) == {
        "src/c7n_hook/config.json",
        "src/c7n_hook/__init__.py",
        "src/c7n_hook/handlers.py",
        "target-info.json",
        "target-schemas/aws-lambda-function.json",
        "configuration-schema.json",
        "schema.json",
        ".rpdk-config",
        ".cfn_metadata.json",
    }

    with open("export.zip", "wb") as fh:
        fh.write(archive.get_bytes())
