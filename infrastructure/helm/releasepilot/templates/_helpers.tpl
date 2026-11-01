{{- define "releasepilot.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "releasepilot.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "releasepilot.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "releasepilot.labels" -}}
app.kubernetes.io/name: {{ include "releasepilot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "releasepilot.selectorLabels" -}}
app.kubernetes.io/name: {{ include "releasepilot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "releasepilot.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "releasepilot.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "releasepilot.secretName" -}}
{{- if .Values.secrets.create -}}
{{- include "releasepilot.fullname" . }}-secrets
{{- else -}}
{{- required "secrets.existingSecret is required when secrets.create is false" .Values.secrets.existingSecret -}}
{{- end -}}
{{- end -}}
