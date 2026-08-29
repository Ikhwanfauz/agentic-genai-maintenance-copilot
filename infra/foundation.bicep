targetScope = 'resourceGroup'

@description('Azure region for temporary V8 resources.')
param location string = resourceGroup().location

@description('UTC date after which the temporary resources should be deleted.')
param deleteAfter string

var baseName = 'maintenance-copilot-v8'
var uniqueSuffix = uniqueString(resourceGroup().id)
var runtimeStorageName = 'runtime'
var acrPullRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7f951dda-4ed3-4680-a7ca-43fe172d538d'
)

var commonTags = {
  project: 'agentic-genai-maintenance-copilot'
  phase: 'V8.4'
  environment: 'temporary-demo'
  lifecycle: 'temporary'
  deleteAfter: deleteAfter
  managedBy: 'bicep'
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${baseName}-${uniqueSuffix}'
  location: location
  tags: commonTags
  properties: {
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acrmcopilot${uniqueSuffix}'
  location: location
  tags: commonTags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    dataEndpointEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stmcopilot${uniqueSuffix}'
  location: location
  tags: commonTags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource runtimeFileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: 'maintenance-runtime'
  properties: {
    accessTier: 'TransactionOptimized'
    enabledProtocols: 'SMB'
    shareQuota: 5
  }
}

resource imagePullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${baseName}-${uniqueSuffix}'
  location: location
  tags: commonTags
}

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, imagePullIdentity.id, acrPullRoleDefinitionId)
  scope: containerRegistry
  properties: {
    principalId: imagePullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRoleDefinitionId
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${baseName}-${uniqueSuffix}'
  location: location
  tags: commonTags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

resource environmentRuntimeStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerAppsEnvironment
  name: runtimeStorageName
  properties: {
    azureFile: {
      accessMode: 'ReadWrite'
      accountKey: storageAccount.listKeys().keys[0].value
      accountName: storageAccount.name
      shareName: runtimeFileShare.name
    }
  }
}

output containerAppsEnvironmentName string = containerAppsEnvironment.name
output containerRegistryLoginServer string = containerRegistry.properties.loginServer
output containerRegistryName string = containerRegistry.name
output imagePullIdentityId string = imagePullIdentity.id
output imageRepository string = '${containerRegistry.properties.loginServer}/maintenance-copilot'
output runtimeStorageName string = environmentRuntimeStorage.name
output storageAccountName string = storageAccount.name
