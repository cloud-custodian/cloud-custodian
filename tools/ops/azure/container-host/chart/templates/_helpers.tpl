
{{- define "azureContainerHostLabels" -}}
cloudcustodian.io/azure-container-host: "cloud-custodian"
cloudcustodian.io/name: "{{ .name }}"
{{- end -}}

{{- define "azureTargetSubscriptionLabel" -}}
{{- if .environment.AZURE_SUBSCRIPTION_ID -}}
cloudcustodian.io/azure-target-subscription-id: "{{ .environment.AZURE_SUBSCRIPTION_ID }}"
{{- end -}}
{{- end -}}
