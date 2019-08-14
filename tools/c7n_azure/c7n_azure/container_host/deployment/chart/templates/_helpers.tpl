{{- define "azureTargetSubscriptionLabel" -}}
{{- if .Values.environment.AZURE_SUBSCRIPTION_ID -}}
cloudcustodian.io/azure-target-subscription-id: "{{ .Values.environment.AZURE_SUBSCRIPTION_ID }}"
{{- end -}}
{{- end -}}
