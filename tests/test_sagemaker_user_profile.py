# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy
import time
import typing

import botocore.client

import pytest
from pytest_terraform import terraform

from c7n.exceptions import PolicyValidationError
from c7n.resources import sagemaker

from .apicallcaptor import ApiCallCaptor


def test_sagemaker_user_profile_update_validate():
    # Accept mutable app defaults, but reject creation-only POSIX settings.
    action = sagemaker.UpdateSagemakerUserProfile({
        'type': 'update',
        'UserSettings': {
            'KernelGatewayAppSettings': {
                'DefaultResourceSpec': {'InstanceType': 'ml.t3.medium'},
            },
        },
    })
    action.validate()

    action.data['UserSettings'] = {'CustomPosixUserConfig': {'Uid': 10000, 'Gid': 1001}}
    with pytest.raises(PolicyValidationError):
        action.validate()


def test_sagemaker_user_profile_schema_older_sdk():
    # Older SDKs may lack both top-level settings and nested resource-spec fields.
    shape = copy.deepcopy(sagemaker.get_service_shape('sagemaker', 'UserSettings'))
    shape.members.pop('AutoMountHomeEFS', None)
    shape.members['KernelGatewayAppSettings'].members[
        'DefaultResourceSpec'].members.pop('LifecycleConfigArn', None)
    schema = copy.deepcopy(sagemaker.UpdateSagemakerUserProfile.schema)
    schema['properties']['UserSettings'] = sagemaker._user_profile_schema(shape, {
        'AutoMountHomeEFS': None,
        'KernelGatewayAppSettings': {
            'DefaultResourceSpec': {'InstanceType': None, 'LifecycleConfigArn': None},
        },
    })
    settings = {
        'KernelGatewayAppSettings': {
            'DefaultResourceSpec': {'InstanceType': 'ml.t3.medium'},
        },
    }
    action = sagemaker.UpdateSagemakerUserProfile({
        'type': 'update',
        'UserSettings': settings,
    })
    action.schema = schema
    action.validate()

    # Missing SDK fields must be rejected, not silently dropped from an update.
    for unavailable in (
        {'AutoMountHomeEFS': 'Disabled'},
        {'KernelGatewayAppSettings': {'DefaultResourceSpec': {'LifecycleConfigArn': 'None'}}},
    ):
        action.data['UserSettings'] = unavailable
        with pytest.raises(PolicyValidationError):
            action.validate()


@pytest.mark.audited
@terraform('sagemaker_user_profile_update', scope='module')
def test_sagemaker_user_profile_update(test, sagemaker_user_profile_update):
    factory = test.replay_flight_data('test_sagemaker_user_profile_update')
    client = factory().client('sagemaker')
    domain_id = sagemaker_user_profile_update['aws_sagemaker_domain.main.id']
    profile_name = sagemaker_user_profile_update[
        'aws_sagemaker_user_profile.main.user_profile_name']
    # Exercise the documented GPU filter and change all three app defaults to CPU.
    apps = (
        'KernelGatewayAppSettings',
        'JupyterLabAppSettings',
        'CodeEditorAppSettings',
    )
    before = client.describe_user_profile(
        DomainId=domain_id,
        UserProfileName=profile_name,
    )['UserSettings']
    for app in apps:
        assert before[app]['DefaultResourceSpec']['InstanceType'] == 'ml.g4dn.xlarge'
    user_settings = {
        app: {'DefaultResourceSpec': {'InstanceType': 'ml.t3.medium'}}
        for app in apps
    }
    policy = test.load_policy(
        {
            'name': 'sagemaker-user-profile-cpu-default',
            'resource': 'aws.sagemaker-user-profile',
            'filters': [
                {'DomainId': domain_id},
                {'UserProfileName': profile_name},
                {
                    'type': 'value',
                    'key': ('UserSettings.KernelGatewayAppSettings.'
                            'DefaultResourceSpec.InstanceType'),
                    'op': 'regex',
                    'value': '^ml[.](g|p)[a-z0-9.]+$',
                },
            ],
            'actions': [{
                'type': 'update',
                'UserSettings': copy.deepcopy(user_settings),
            }],
        },
        session_factory=factory,
    )
    captor = ApiCallCaptor.start_capture()
    [resource] = policy.run()
    assert resource['UserProfileName'] == profile_name
    assert [
        call['params'] for call in captor.calls
        if call.get('operation') == 'UpdateUserProfile'
    ] == [{
        'DomainId': domain_id,
        'UserProfileName': profile_name,
        'UserSettings': user_settings,
    }]
    for _ in range(60):
        updated = client.describe_user_profile(
            DomainId=domain_id,
            UserProfileName=profile_name,
        )
        if updated['Status'] == 'InService':
            break
        if test.recording:
            time.sleep(5)
    assert updated['Status'] == 'InService'
    settings = updated['UserSettings']
    for app in apps:
        assert settings[app]['DefaultResourceSpec']['InstanceType'] == 'ml.t3.medium'
    # Updating instance defaults must preserve unrelated user and app settings.
    assert settings['ExecutionRole'] == before['ExecutionRole']
    assert settings['JupyterLabAppSettings']['CodeRepositories'] == [{
        'RepositoryUrl': 'https://github.com/cloud-custodian/cloud-custodian',
    }]


def describe_user_profile(
    test: typing.Any,
    client: botocore.client.BaseClient,
    domain_id: str,
    profile_name: str,
) -> dict:
    # Creation and updates are asynchronous; read settings only after completion.
    for _ in range(60):
        profile = client.describe_user_profile(
            DomainId=domain_id,
            UserProfileName=profile_name,
        )
        status = profile['Status']
        assert status in ('Pending', 'Updating', 'InService'), profile.get('FailureReason')
        if status == 'InService':
            break
        if test.recording:
            time.sleep(5)
    assert profile['Status'] == 'InService'
    return profile


def update_user_profile(
    test: typing.Any,
    factory: typing.Callable,
    domain_id: str,
    profile_name: str,
    settings: dict,
) -> dict:
    # Isolate expected values so action-side mutation cannot weaken the assertions.
    policy = test.load_policy(
        {
            'name': 'update-user-profile-settings',
            'resource': 'aws.sagemaker-user-profile',
            'filters': [
                {'DomainId': domain_id},
                {'UserProfileName': profile_name},
            ],
            'actions': [{'type': 'update', 'UserSettings': copy.deepcopy(settings)}],
        },
        session_factory=factory,
    )
    # Matching replayed readback alone must not let a missing SDK update pass.
    captor = ApiCallCaptor.start_capture()
    [resource] = policy.run()
    assert resource['UserProfileName'] == profile_name
    assert [
        call['params'] for call in captor.calls
        if call.get('operation') == 'UpdateUserProfile'
    ] == [{
        'DomainId': domain_id,
        'UserProfileName': profile_name,
        'UserSettings': settings,
    }]
    return describe_user_profile(
        test,
        factory().client('sagemaker'),
        domain_id,
        profile_name,
    )['UserSettings']


@pytest.mark.audited
@terraform('sagemaker_user_profile_update', scope='module')
def test_sagemaker_user_profile_update_settings(test, sagemaker_user_profile_update):
    fixture = sagemaker_user_profile_update
    factory = test.replay_flight_data('test_sagemaker_user_profile_update_settings')
    client = factory().client('sagemaker')
    domain_id = fixture['aws_sagemaker_domain.main.id']
    profile_name = fixture['aws_sagemaker_user_profile.settings.user_profile_name']
    before = describe_user_profile(test, client, domain_id, profile_name)['UserSettings']
    # Distinct initial role/group values make replacement checks detect no-ops.
    assert before['ExecutionRole'] == fixture['aws_iam_role.execution.arn']
    assert fixture['aws_security_group.initial.id'] in before['SecurityGroups']
    sharing = {
        'NotebookOutputOption': 'Allowed',
        'S3OutputPath': f"s3://{fixture['aws_s3_bucket.sharing.bucket']}/notebooks/",
        'S3KmsKeyId': fixture['aws_kms_key.sharing.arn'],
    }
    storage = {
        'DefaultEbsStorageSettings': {
            'DefaultEbsVolumeSizeInGb': 10,
            'MaximumEbsVolumeSizeInGb': 30,
        },
    }
    portal = {
        'HiddenMlTools': ['DataWrangler'],
        'HiddenAppTypes': ['TensorBoard'],
        'HiddenInstanceTypes': ['ml.g4dn.xlarge'],
        'HiddenSageMakerImageVersionAliases': [{
            'SageMakerImageName': 'sagemaker_distribution',
            'VersionAliases': ['2.0'],
        }],
        'ExecutionRoleSessionNameMode': 'USER_IDENTITY',
    }
    updated = update_user_profile(
        test,
        factory,
        domain_id,
        profile_name,
        {
            'ExecutionRole': fixture['aws_iam_role.updated_execution.arn'],
            'SecurityGroups': [fixture['aws_security_group.updated.id']],
            'SharingSettings': sharing,
            'DefaultLandingUri': 'studio::',
            'StudioWebPortal': 'ENABLED',
            'SpaceStorageSettings': storage,
            'AutoMountHomeEFS': 'Disabled',
            'StudioWebPortalSettings': portal,
        },
    )
    assert updated['ExecutionRole'] == fixture['aws_iam_role.updated_execution.arn']
    assert fixture['aws_security_group.updated.id'] in updated['SecurityGroups']
    assert fixture['aws_security_group.initial.id'] not in updated['SecurityGroups']
    assert updated['SharingSettings'] == sharing
    assert updated['DefaultLandingUri'] == 'studio::'
    assert updated['StudioWebPortal'] == 'ENABLED'
    assert updated['SpaceStorageSettings'] == storage
    assert updated['AutoMountHomeEFS'] == 'Disabled'
    assert updated['StudioWebPortalSettings'] == portal

    # Reverse the toggles and remove populated visibility lists, not just omit them.
    cleared = update_user_profile(
        test,
        factory,
        domain_id,
        profile_name,
        {
            'StudioWebPortal': 'DISABLED',
            'DefaultLandingUri': 'app:JupyterServer:',
            'AutoMountHomeEFS': 'Enabled',
            'SharingSettings': {'NotebookOutputOption': 'Disabled'},
            'StudioWebPortalSettings': {
                'HiddenMlTools': [],
                'HiddenAppTypes': [],
                'HiddenInstanceTypes': [],
                'HiddenSageMakerImageVersionAliases': [],
                'ExecutionRoleSessionNameMode': 'STATIC',
            },
        },
    )
    assert cleared['StudioWebPortal'] == 'DISABLED'
    assert cleared['DefaultLandingUri'] == 'app:JupyterServer:'
    assert cleared['AutoMountHomeEFS'] == 'Enabled'
    assert cleared['SharingSettings']['NotebookOutputOption'] == 'Disabled'
    assert cleared['StudioWebPortalSettings'] == {
        'HiddenMlTools': [],
        'HiddenAppTypes': [],
        'HiddenInstanceTypes': [],
        'HiddenSageMakerImageVersionAliases': [],
        'ExecutionRoleSessionNameMode': 'STATIC',
    }


@pytest.mark.audited
@terraform('sagemaker_user_profile_update', scope='module')
def test_sagemaker_user_profile_update_rstudio(test, sagemaker_user_profile_update):
    fixture = sagemaker_user_profile_update
    factory = test.replay_flight_data('test_sagemaker_user_profile_update_rstudio')
    domain_id = fixture['aws_sagemaker_domain.main.id']
    profile_name = fixture['aws_sagemaker_user_profile.rstudio.user_profile_name']
    before = describe_user_profile(
        test,
        factory().client('sagemaker'),
        domain_id,
        profile_name,
    )['UserSettings']
    # RStudio permits group selection only when access is enabled for the first time.
    assert before['RStudioServerProAppSettings']['AccessStatus'] == 'DISABLED'
    updated = update_user_profile(
        test,
        factory,
        domain_id,
        profile_name,
        {
            'RStudioServerProAppSettings': {
                'AccessStatus': 'ENABLED',
                'UserGroup': 'R_STUDIO_ADMIN',
            },
        },
    )
    assert updated['RStudioServerProAppSettings'] == {
        'AccessStatus': 'ENABLED',
        'UserGroup': 'R_STUDIO_ADMIN',
    }


@pytest.mark.audited
@terraform('sagemaker_user_profile_update', scope='module')
def test_sagemaker_user_profile_update_canvas_settings(
    test,
    sagemaker_user_profile_update,
):
    fixture = sagemaker_user_profile_update
    factory = test.replay_flight_data('test_sagemaker_user_profile_update_canvas_settings')
    domain_id = fixture['aws_sagemaker_domain.main.id']
    profile_name = fixture['aws_sagemaker_user_profile.canvas.user_profile_name']
    # Check every Canvas setting, including role, storage, and OAuth references.
    canvas = {
        'TimeSeriesForecastingSettings': {
            'Status': 'ENABLED',
            'AmazonForecastRoleArn': fixture['aws_iam_role.canvas.arn'],
        },
        'ModelRegisterSettings': {
            'Status': 'ENABLED',
            'CrossAccountModelRegisterRoleArn': fixture['aws_iam_role.canvas.arn'],
        },
        'WorkspaceSettings': {
            'S3ArtifactPath': f"s3://{fixture['aws_s3_bucket.sharing.bucket']}/canvas/",
            'S3KmsKeyId': fixture['aws_kms_key.sharing.arn'],
        },
        'IdentityProviderOAuthSettings': [{
            'DataSourceName': 'Snowflake',
            'Status': 'ENABLED',
            'SecretArn': fixture['aws_secretsmanager_secret.oauth.arn'],
        }],
        'DirectDeploySettings': {'Status': 'ENABLED'},
        'KendraSettings': {'Status': 'ENABLED'},
        'GenerativeAiSettings': {
            'AmazonBedrockRoleArn': fixture['aws_iam_role.canvas.arn'],
        },
        'EmrServerlessSettings': {
            'Status': 'ENABLED',
            'ExecutionRoleArn': fixture['aws_iam_role.canvas.arn'],
        },
    }
    updated = update_user_profile(
        test,
        factory,
        domain_id,
        profile_name,
        {'CanvasAppSettings': canvas},
    )
    assert updated['CanvasAppSettings'] == canvas
    # Disable assigned integrations and remove the previously populated OAuth list.
    disabled = {
        'TimeSeriesForecastingSettings': {'Status': 'DISABLED'},
        'ModelRegisterSettings': {'Status': 'DISABLED'},
        'DirectDeploySettings': {'Status': 'DISABLED'},
        'KendraSettings': {'Status': 'DISABLED'},
        'EmrServerlessSettings': {'Status': 'DISABLED'},
        'IdentityProviderOAuthSettings': [],
    }
    updated = update_user_profile(
        test,
        factory,
        domain_id,
        profile_name,
        {'CanvasAppSettings': disabled},
    )
    for app, settings in disabled.items():
        if app == 'IdentityProviderOAuthSettings':
            assert updated['CanvasAppSettings'][app] == []
        else:
            assert updated['CanvasAppSettings'][app]['Status'] == settings['Status']


def assert_settings(actual: dict, expected: dict) -> None:
    # Compare requested fields while allowing additional service-provided defaults.
    for name, value in expected.items():
        if isinstance(value, dict):
            assert_settings(actual[name], value)
        else:
            assert actual[name] == value, name


@pytest.mark.audited
@terraform('sagemaker_user_profile_update', scope='module')
def test_sagemaker_user_profile_update_app_settings(test, sagemaker_user_profile_update):
    fixture = sagemaker_user_profile_update
    factory = test.replay_flight_data('test_sagemaker_user_profile_update_app_settings')
    domain_id = fixture['aws_sagemaker_domain.main.id']
    profile_name = fixture['aws_sagemaker_user_profile.app.user_profile_name']
    lifecycle_configs = fixture.outputs['lifecycle_configs']['value']
    apps = {
        'JupyterServerAppSettings': 'JupyterServer',
        'KernelGatewayAppSettings': 'KernelGateway',
        'TensorBoardAppSettings': 'TensorBoard',
        'RSessionAppSettings': 'RSessionGateway',
        'CodeEditorAppSettings': 'CodeEditor',
        'JupyterLabAppSettings': 'JupyterLab',
    }
    settings = {}
    clear = {}
    # Shared API shapes do not imply that every app supports the same settings.
    for app, app_type in apps.items():
        # JupyterServer requires a managed image and the system instance type.
        instance_type = 'system' if app_type == 'JupyterServer' else 'ml.t3.medium'
        image_arn = fixture['aws_sagemaker_image.app.arn']
        if app_type == 'JupyterServer':
            image_arn = fixture.outputs['jupyter_server_image']['value']
        spec = {'SageMakerImageArn': image_arn, 'InstanceType': instance_type}
        app_settings = {'DefaultResourceSpec': spec}
        app_clear = {}
        if app in lifecycle_configs:
            lifecycle = lifecycle_configs[app]
            spec['LifecycleConfigArn'] = lifecycle['default']
            app_settings['LifecycleConfigArns'] = [lifecycle['default']]
            app_clear['LifecycleConfigArns'] = []
            app_clear['DefaultResourceSpec'] = {'InstanceType': instance_type}
            # JupyterServer clears the default by omission; other apps accept 'None'.
            if app_type != 'JupyterServer':
                app_clear['DefaultResourceSpec']['LifecycleConfigArn'] = 'None'
        if app_type in ('KernelGateway', 'RSessionGateway', 'CodeEditor', 'JupyterLab'):
            app_settings['CustomImages'] = [{
                'ImageName': fixture['aws_sagemaker_image.app.image_name'],
                'ImageVersionNumber': fixture['aws_sagemaker_image_version.updated.version'],
                'AppImageConfigName': fixture.outputs['app_image_configs']['value'][app_type],
            }]
            app_clear['CustomImages'] = []
        if app_type in ('JupyterServer', 'JupyterLab'):
            app_settings['CodeRepositories'] = [{
                'RepositoryUrl': 'https://github.com/cloud-custodian/cloud-custodian',
            }]
            app_clear['CodeRepositories'] = []
        if app_type in ('JupyterLab', 'CodeEditor'):
            app_settings['BuiltInLifecycleConfigArn'] = lifecycle_configs[app]['builtin']
            app_settings['AppLifecycleManagement'] = {'IdleSettings': {
                'LifecycleManagement': 'ENABLED',
                'IdleTimeoutInMinutes': 120,
                'MinIdleTimeoutInMinutes': 60,
                'MaxIdleTimeoutInMinutes': 240,
            }}
            app_clear['AppLifecycleManagement'] = {'IdleSettings': {
                'LifecycleManagement': 'DISABLED',
            }}
        if app_type == 'JupyterLab':
            app_settings['EmrSettings'] = {
                'AssumableRoleArns': [fixture['aws_iam_role.emr_assumable.arn']],
                'ExecutionRoleArns': [fixture['aws_iam_role.canvas.arn']],
            }
            app_clear['EmrSettings'] = {'AssumableRoleArns': [], 'ExecutionRoleArns': []}
        settings[app] = app_settings
        if app_clear:
            clear[app] = app_clear

    updated = update_user_profile(test, factory, domain_id, profile_name, settings)
    assert_settings(updated, settings)
    assert updated['ExecutionRole'] == fixture['aws_iam_role.execution.arn']

    # Separate image, version-ARN, and alias updates so precedence cannot mask a no-op.
    versioned_apps = (
        'KernelGatewayAppSettings',
        'TensorBoardAppSettings',
        'RSessionAppSettings',
        'CodeEditorAppSettings',
        'JupyterLabAppSettings',
    )
    initial_version = fixture['aws_sagemaker_image_version.initial.arn']
    versions = {
        app: {'DefaultResourceSpec': {'SageMakerImageVersionArn': initial_version}}
        for app in versioned_apps
    }
    updated = update_user_profile(test, factory, domain_id, profile_name, versions)
    assert_settings(updated, versions)
    # Omitting the lifecycle ARN in a resource-spec update removes its default.
    for app in (
        'KernelGatewayAppSettings',
        'CodeEditorAppSettings',
        'JupyterLabAppSettings',
    ):
        assert 'LifecycleConfigArn' not in updated[app]['DefaultResourceSpec']
    # Remove version pins before checking aliases; a pinned ARN takes precedence.
    updated = update_user_profile(
        test,
        factory,
        domain_id,
        profile_name,
        {
            app: {'DefaultResourceSpec': {'SageMakerImageVersionArn': 'None'}}
            for app in versioned_apps
        },
    )
    for app in versioned_apps:
        assert updated[app]['DefaultResourceSpec'].get('SageMakerImageVersionArn') in (
            None,
            'None',
        )
    aliases = {
        app: {'DefaultResourceSpec': {
            'SageMakerImageVersionAlias': '1' if app_type == 'JupyterServer' else '2.0.0',
        }}
        for app, app_type in apps.items()
    }
    # Restore lifecycle defaults so the final clear starts from assigned values.
    for app, lifecycle in lifecycle_configs.items():
        aliases[app]['DefaultResourceSpec']['LifecycleConfigArn'] = lifecycle['default']
    updated = update_user_profile(test, factory, domain_id, profile_name, aliases)
    assert_settings(updated, aliases)
    # Remove populated collections/defaults and disable idle management.
    updated = update_user_profile(test, factory, domain_id, profile_name, clear)
    for app, app_clear in clear.items():
        for field, value in app_clear.items():
            if field == 'DefaultResourceSpec':
                assert updated[app][field].get('LifecycleConfigArn') in (None, 'None')
            else:
                assert_settings(updated[app], {field: value})
