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


def test_foundation_declares_persistent_runtime_storage() -> None:
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
