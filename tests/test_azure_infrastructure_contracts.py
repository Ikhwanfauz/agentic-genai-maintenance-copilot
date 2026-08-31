from pathlib import Path

FOUNDATION_PATH = Path("infra/foundation.bicep")


def load_foundation() -> str:
    return FOUNDATION_PATH.read_text(encoding="utf-8")


def test_foundation_targets_existing_resource_group() -> None:
    foundation = load_foundation()

    assert "targetScope = 'resourceGroup'" in foundation
    assert "param location string = resourceGroup().location" in foundation
    assert "param deleteAfter string" in foundation


def test_foundation_declares_temporary_resource_tags() -> None:
    foundation = load_foundation()

    assert "phase: 'V8.4'" in foundation
    assert "environment: 'temporary-demo'" in foundation
    assert "lifecycle: 'temporary'" in foundation
    assert "deleteAfter: deleteAfter" in foundation
    assert "managedBy: 'bicep'" in foundation


def test_foundation_uses_private_basic_registry() -> None:
    foundation = load_foundation()

    assert "Microsoft.ContainerRegistry/registries" in foundation
    assert "name: 'Basic'" in foundation
    assert "adminUserEnabled: false" in foundation
    assert "dataEndpointEnabled: false" in foundation


def test_foundation_declares_persistent_cache_storage() -> None:
    foundation = load_foundation()

    assert "minimumTlsVersion: 'TLS1_2'" in foundation
    assert "allowBlobPublicAccess: false" in foundation
    assert "name: 'maintenance-runtime'" in foundation
    assert "shareQuota: 5" in foundation
    assert "accessMode: 'ReadWrite'" in foundation


def test_foundation_declares_logs_and_container_environment() -> None:
    foundation = load_foundation()

    assert "Microsoft.OperationalInsights/workspaces" in foundation
    assert "retentionInDays: 30" in foundation
    assert "Microsoft.App/managedEnvironments" in foundation
    assert "destination: 'log-analytics'" in foundation


def test_foundation_uses_managed_identity_for_registry_pull() -> None:
    foundation = load_foundation()

    assert "Microsoft.ManagedIdentity/userAssignedIdentities" in foundation
    assert "Microsoft.Authorization/roleAssignments" in foundation
    assert "7f951dda-4ed3-4680-a7ca-43fe172d538d" in foundation
    assert "principalType: 'ServicePrincipal'" in foundation
    assert "azure_openai_api_key" not in foundation.lower()


APPS_PATH = Path("infra/apps.bicep")


def load_apps() -> str:
    return APPS_PATH.read_text(encoding="utf-8")


def test_apps_require_secure_runtime_parameters() -> None:
    apps = load_apps()

    assert "@secure()" in apps
    assert "param azureOpenAiApiKey string" in apps
    assert "param allowedDashboardIpCidr string" in apps
    assert "value: azureOpenAiApiKey" in apps
    assert "secretRef: 'azure-openai-api-key'" in apps


def test_apps_use_existing_foundation_resources() -> None:
    apps = load_apps()

    assert apps.count(" existing = {") == 3
    assert "Microsoft.App/managedEnvironments" in apps
    assert "Microsoft.ContainerRegistry/registries" in apps
    assert "Microsoft.ManagedIdentity/userAssignedIdentities" in apps


def test_apps_pull_private_image_with_managed_identity() -> None:
    apps = load_apps()

    assert "type: 'UserAssigned'" in apps
    assert "identity: imagePullIdentity.id" in apps
    assert "server: containerRegistry.properties.loginServer" in apps
    assert "/maintenance-copilot:${imageTag}" in apps


def test_api_isolates_locking_stores_from_azure_files() -> None:
    apps = load_apps()

    assert "name: apiAppName" in apps
    assert "external: false" in apps
    assert "value: 'sqlite:////tmp/maintenance_copilot.db'" in apps
    assert "value: '/tmp/langgraph_checkpoints.sqlite'" in apps
    assert "value: '/tmp/chroma'" in apps
    assert "value: '/app/runtime/huggingface'" in apps
    assert "mountPath: '/app/runtime'" in apps
    assert "storageType: 'AzureFile'" in apps
    assert "INITIALIZE_APPLICATION_DATA" in apps
    assert "sqlite:////app/runtime" not in apps
    assert "/app/runtime/langgraph_checkpoints.sqlite" not in apps
    assert "value: '/app/runtime/chroma'" not in apps


def test_dashboard_is_ip_restricted_without_model_secret() -> None:
    apps = load_apps()
    dashboard = apps.split("resource dashboardApp", maxsplit=1)[1]

    assert "external: true" in dashboard
    assert "ipAddressRange: allowedDashboardIpCidr" in dashboard
    assert "name: 'operator-ip'" in dashboard
    assert "AZURE_OPENAI_API_KEY" not in dashboard


def test_apps_are_locked_to_single_replica() -> None:
    apps = load_apps()

    assert apps.count("minReplicas: 1") == 2
    assert apps.count("maxReplicas: 1") == 2


def test_apps_declare_explicit_health_probes() -> None:
    apps = load_apps()

    assert apps.count("type: 'Startup'") == 2
    assert apps.count("type: 'Liveness'") == 2
    assert apps.count("type: 'Readiness'") == 2
    assert "'/_stcore/health'" in apps
