targetScope = 'resourceGroup'

@description('Azure region containing the V8 foundation.')
param location string = resourceGroup().location

@description('Existing Container Apps environment name.')
param containerAppsEnvironmentName string

@description('Existing Azure Container Registry name.')
param containerRegistryName string

@description('Existing image-pull managed identity name.')
param imagePullIdentityName string

@description('Container image tag already pushed to ACR.')
param imageTag string

@description('Existing Container Apps environment storage registration.')
param runtimeStorageName string = 'runtime'

@description('Azure OpenAI endpoint used by the API.')
param azureOpenAiEndpoint string

@secure()
@description('Azure OpenAI API key stored as a Container App secret.')
param azureOpenAiApiKey string

@description('Azure OpenAI deployment name.')
param azureOpenAiDeployment string = 'gpt-5.4-mini'

@description('Single IPv4 CIDR allowed to access the dashboard.')
param allowedDashboardIpCidr string

@description('UTC date after which the temporary resources should be deleted.')
param deleteAfter string

var apiAppName = 'ca-maintenance-copilot-api'
var dashboardAppName = 'ca-maintenance-copilot-dashboard'
var imageName = '${containerRegistry.properties.loginServer}/maintenance-copilot:${imageTag}'

var commonTags = {
  project: 'agentic-genai-maintenance-copilot'
  phase: 'V8.4'
  environment: 'temporary-demo'
  lifecycle: 'temporary'
  deleteAfter: deleteAfter
  managedBy: 'bicep'
}

var apiProbes = [
  {
    type: 'Startup'
    httpGet: {
      path: '/health'
      port: 8000
      scheme: 'HTTP'
    }
    initialDelaySeconds: 5
    periodSeconds: 10
    timeoutSeconds: 5
    failureThreshold: 30
    successThreshold: 1
  }
  {
    type: 'Liveness'
    httpGet: {
      path: '/health'
      port: 8000
      scheme: 'HTTP'
    }
    initialDelaySeconds: 30
    periodSeconds: 30
    timeoutSeconds: 5
    failureThreshold: 3
    successThreshold: 1
  }
  {
    type: 'Readiness'
    httpGet: {
      path: '/health'
      port: 8000
      scheme: 'HTTP'
    }
    initialDelaySeconds: 10
    periodSeconds: 10
    timeoutSeconds: 5
    failureThreshold: 6
    successThreshold: 1
  }
]

var dashboardProbes = [
  {
    type: 'Startup'
    httpGet: {
      path: '/_stcore/health'
      port: 8501
      scheme: 'HTTP'
    }
    initialDelaySeconds: 5
    periodSeconds: 5
    timeoutSeconds: 3
    failureThreshold: 30
    successThreshold: 1
  }
  {
    type: 'Liveness'
    httpGet: {
      path: '/_stcore/health'
      port: 8501
      scheme: 'HTTP'
    }
    initialDelaySeconds: 20
    periodSeconds: 30
    timeoutSeconds: 3
    failureThreshold: 3
    successThreshold: 1
  }
  {
    type: 'Readiness'
    httpGet: {
      path: '/_stcore/health'
      port: 8501
      scheme: 'HTTP'
    }
    initialDelaySeconds: 10
    periodSeconds: 10
    timeoutSeconds: 3
    failureThreshold: 6
    successThreshold: 1
  }
]

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: containerAppsEnvironmentName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

resource imagePullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: imagePullIdentityName
}

resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiAppName
  location: location
  tags: commonTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${imagePullIdentity.id}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        allowInsecure: false
        external: false
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          identity: imagePullIdentity.id
          server: containerRegistry.properties.loginServer
        }
      ]
      secrets: [
        {
          name: 'azure-openai-api-key'
          value: azureOpenAiApiKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: imageName
          env: [
            {
              name: 'APP_ENV'
              value: 'production'
            }
            {
              name: 'INITIALIZE_APPLICATION_DATA'
              value: 'true'
            }
            // SQLite-backed application, checkpoint, and Chroma state use
            // replica-local storage because Azure Files SMB does not provide
            // the file-locking semantics required by these components.
            {
              name: 'DATABASE_URL'
              value: 'sqlite:////tmp/maintenance_copilot.db'
            }
            {
              name: 'LANGGRAPH_CHECKPOINT_PATH'
              value: '/tmp/langgraph_checkpoints.sqlite'
            }
            {
              name: 'ENGINEERING_DOCS_PATH'
              value: '/app/data/engineering_docs'
            }
            {
              name: 'VECTOR_STORE_PATH'
              value: '/tmp/chroma'
            }
            {
              name: 'HF_HOME'
              value: '/app/runtime/huggingface'
            }
            {
              name: 'LLM_PROVIDER'
              value: 'azure_openai'
            }
            {
              name: 'LLM_MODEL'
              value: azureOpenAiDeployment
            }
            {
              name: 'LLM_REASONING_EFFORT'
              value: 'low'
            }
            {
              name: 'LLM_TIMEOUT_SECONDS'
              value: '30'
            }
            {
              name: 'LLM_MAX_RETRIES'
              value: '2'
            }
            {
              name: 'AZURE_OPENAI_API_KEY'
              secretRef: 'azure-openai-api-key'
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: azureOpenAiEndpoint
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT'
              value: azureOpenAiDeployment
            }
          ]
          probes: apiProbes
          resources: {
            cpu: 1
            memory: '2Gi'
          }
          volumeMounts: [
            {
              mountPath: '/app/runtime'
              volumeName: 'runtime'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
      terminationGracePeriodSeconds: 30
      volumes: [
        {
          name: 'runtime'
          storageName: runtimeStorageName
          storageType: 'AzureFile'
        }
      ]
    }
  }
}

resource dashboardApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: dashboardAppName
  location: location
  tags: commonTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${imagePullIdentity.id}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        allowInsecure: false
        external: true
        targetPort: 8501
        transport: 'auto'
        ipSecurityRestrictions: [
          {
            action: 'Allow'
            description: 'Temporary V8 operator access'
            ipAddressRange: allowedDashboardIpCidr
            name: 'operator-ip'
          }
        ]
      }
      registries: [
        {
          identity: imagePullIdentity.id
          server: containerRegistry.properties.loginServer
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'dashboard'
          image: imageName
          command: [
            'python'
            '-m'
            'app.container_startup'
          ]
          args: [
            'python'
            '-m'
            'streamlit'
            'run'
            'streamlit_app.py'
            '--server.address=0.0.0.0'
            '--server.port=8501'
            '--server.headless=true'
            '--browser.gatherUsageStats=false'
          ]
          env: [
            {
              name: 'APP_ENV'
              value: 'production'
            }
            {
              name: 'INITIALIZE_APPLICATION_DATA'
              value: 'false'
            }
            {
              name: 'MAINTENANCE_API_BASE_URL'
              value: 'https://${apiApp.properties.configuration.ingress.fqdn}'
            }
            {
              name: 'MAINTENANCE_API_TIMEOUT_SECONDS'
              value: '120'
            }
          ]
          probes: dashboardProbes
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
      terminationGracePeriodSeconds: 30
    }
  }
}

output apiFqdn string = apiApp.properties.configuration.ingress.fqdn
output dashboardFqdn string = dashboardApp.properties.configuration.ingress.fqdn
output dashboardUrl string = 'https://${dashboardApp.properties.configuration.ingress.fqdn}'
output imageReference string = imageName
