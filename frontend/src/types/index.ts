export interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'operator' | 'developer' | 'viewer';
  is_active: boolean;
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  git_repo: string;
  default_branch: string;
  image_repository: string;
  default_port: number;
  health_path: string;
  owner_id?: string;
  created_at: string;
  updated_at: string;
}

export interface Environment {
  id: string;
  project_id: string;
  name: string;
  k8s_namespace: string;
  k8s_cluster: string;
  replicas: number;
  deployment_strategy: 'rolling' | 'canary';
  canary_steps: number[];
  auto_rollback_enabled: boolean;
  verification_timeout_seconds: number;
  verification_attempts: number;
  smoke_test_endpoint: string;
  smoke_test_expected_status: number;
  smoke_test_timeout_seconds: number;
  env_vars: Record<string, string>;
  current_release_id?: string;
  created_at: string;
  updated_at: string;
}

export interface Release {
  id: string;
  project_id: string;
  version: string;
  git_commit: string;
  git_branch: string;
  image_tag: string;
  commit_message?: string;
  changelog?: string;
  scan_status: 'unscanned' | 'clean' | 'warning' | 'critical';
  scan_results: Record<string, any>;
  created_at: string;
}

export interface DeploymentLog {
  timestamp: string;
  level: string;
  message: string;
}

export interface Deployment {
  id: string;
  project_id: string;
  environment_id: string;
  release_id: string;
  triggered_by?: string;
  status: 'pending' | 'scanning' | 'deploying' | 'verifying' | 'active' | 'failed' | 'rolled_back' | 'rolling_back' | 'cancelled';
  strategy: string;
  progress: number;
  is_simulated: boolean;
  adapter_name: string;
  logs: DeploymentLog[];
  metadata_info: Record<string, any>;
  started_at: string;
  finished_at?: string;
  idempotency_key?: string;
}

export interface HealthCheck {
  id: string;
  deployment_id: string;
  check_type: string;
  status: 'passed' | 'failed' | 'warning';
  status_code?: number;
  latency_ms?: number;
  details: Record<string, any>;
  executed_at: string;
}

export interface RollbackEvent {
  id: string;
  source_deployment_id: string;
  environment_id: string;
  failed_release_id: string;
  restored_release_id: string;
  is_automated: boolean;
  triggered_by_user_id?: string;
  reason: string;
  status: string;
  details: Record<string, any>;
  created_at: string;
}

export interface SystemStats {
  total_projects: number;
  total_environments: number;
  total_deployments: number;
  active_deployments: number;
  failed_deployments: number;
  rollback_count: number;
  success_rate_pct: number;
  mttr_minutes: number;
}

export interface AuditLog {
  id: string;
  user_id?: string;
  username?: string;
  action: string;
  entity_type: string;
  entity_id: string;
  ip_address?: string;
  details: Record<string, any>;
  created_at: string;
}
