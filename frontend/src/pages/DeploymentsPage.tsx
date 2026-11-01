import React, { useState, useEffect } from 'react';
import api from '../api/client';
import { Deployment, Project, Environment, Release, HealthCheck } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { GitBranch, RotateCcw, Terminal, Activity, CheckCircle2, AlertTriangle, Cpu, Layers } from 'lucide-react';
import { RollbackModal } from '../components/RollbackModal';

interface DeploymentsPageProps {
  initialSelectedId?: string | null;
}

export const DeploymentsPage: React.FC<DeploymentsPageProps> = ({ initialSelectedId }) => {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [selectedDep, setSelectedDep] = useState<Deployment | null>(null);
  const [healthChecks, setHealthChecks] = useState<HealthCheck[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [releases, setReleases] = useState<Release[]>([]);
  const [filter, setFilter] = useState<string>('all');
  const [showRollbackModal, setShowRollbackModal] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadAll = async () => {
    try {
      const [depRes, projRes] = await Promise.all([
        api.get('/deployments?limit=50'),
        api.get('/projects')
      ]);
      setDeployments(depRes.data.data);
      setProjects(projRes.data.data);

      if (depRes.data.data.length > 0) {
        if (initialSelectedId) {
          const match = depRes.data.data.find((d: Deployment) => d.id === initialSelectedId);
          setSelectedDep(match || depRes.data.data[0]);
        } else if (!selectedDep) {
          setSelectedDep(depRes.data.data[0]);
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadDeploymentDetails = async (depId: string) => {
    try {
      const [depRes, hcRes] = await Promise.all([
        api.get(`/deployments/${depId}`),
        api.get(`/deployments/${depId}/health-checks`)
      ]);
      setSelectedDep(depRes.data.data);
      setHealthChecks(hcRes.data.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadAll();
    const interval = setInterval(() => {
      loadAll();
      if (selectedDep) {
        loadDeploymentDetails(selectedDep.id);
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [selectedDep?.id]);

  const filteredDeployments = deployments.filter((d) => {
    if (filter === 'all') return true;
    return d.status === filter;
  });

  const getProjectName = (projId: string) => projects.find((p) => p.id === projId)?.name || projId;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">Deployments Console</h1>
          <p className="text-sm text-slate-400">
            Real-time pipeline orchestration, rolling/canary status, and automated rollback telemetry.
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 p-1 bg-slate-900 border border-slate-800 rounded-xl overflow-x-auto">
          {['all', 'active', 'deploying', 'rolled_back', 'failed'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize whitespace-nowrap transition-all ${
                filter === f
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {f.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Deployment List */}
        <div className="lg:col-span-5 space-y-3">
          {filteredDeployments.map((dep) => (
            <div
              key={dep.id}
              onClick={() => {
                setSelectedDep(dep);
                loadDeploymentDetails(dep.id);
              }}
              className={`p-4 rounded-xl glass-card cursor-pointer transition-all ${
                selectedDep?.id === dep.id
                  ? 'border-emerald-500/50 bg-slate-900/90 shadow-md shadow-emerald-500/5'
                  : 'glass-card-hover'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="font-bold text-sm text-white">{getProjectName(dep.project_id)}</div>
                <StatusBadge status={dep.status} size="sm" />
              </div>

              <div className="flex items-center justify-between text-xs text-slate-400">
                <span className="capitalize">Strategy: <strong className="text-slate-300">{dep.strategy}</strong></span>
                <span className="font-mono text-[11px] text-slate-400">{new Date(dep.started_at).toLocaleTimeString()}</span>
              </div>

              <div className="mt-2.5 w-full bg-slate-800/80 rounded-full h-1 overflow-hidden">
                <div
                  className={`h-full ${
                    dep.status === 'failed' ? 'bg-rose-500' :
                    dep.status === 'rolled_back' ? 'bg-purple-500' : 'bg-emerald-500'
                  }`}
                  style={{ width: `${dep.progress}%` }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Right Column: Detailed Inspector */}
        <div className="lg:col-span-7">
          {selectedDep ? (
            <div className="p-6 rounded-2xl glass-card space-y-6">
              {/* Header and Rollback Action */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-extrabold text-white">
                      {getProjectName(selectedDep.project_id)}
                    </h2>
                    <StatusBadge status={selectedDep.status} />
                  </div>
                  <p className="text-xs text-slate-400 font-mono mt-1">
                    Deployment ID: {selectedDep.id}
                  </p>
                </div>

                {/* Emergency Rollback button */}
                {['active', 'deploying', 'verifying'].includes(selectedDep.status) && (
                  <button
                    onClick={() => setShowRollbackModal(true)}
                    className="px-4 py-2 rounded-xl text-xs font-bold bg-purple-500/15 text-purple-300 border border-purple-500/30 hover:bg-purple-500/25 transition-all flex items-center gap-2 self-start sm:self-auto shadow-sm"
                  >
                    <RotateCcw className="w-3.5 h-3.5 text-purple-400" />
                    <span>Trigger Rollback</span>
                  </button>
                )}
              </div>

              {/* Execution Info & Adapter Spec */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl">
                  <div className="text-[11px] text-slate-400 uppercase font-semibold">Strategy</div>
                  <div className="text-sm font-bold text-white capitalize">{selectedDep.strategy}</div>
                </div>
                <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl">
                  <div className="text-[11px] text-slate-400 uppercase font-semibold">Adapter</div>
                  <div className="text-sm font-mono font-bold text-emerald-400">{selectedDep.adapter_name}</div>
                </div>
                <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl">
                  <div className="text-[11px] text-slate-400 uppercase font-semibold">Telemetry Mode</div>
                  <div className="text-sm font-bold text-slate-200">
                    {selectedDep.is_simulated ? (
                      <span className="text-amber-400">Simulated Adapter</span>
                    ) : (
                      <span className="text-emerald-400">Live Cluster</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Synthetic Health Checks Section */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                    <Activity className="w-4 h-4 text-emerald-400" />
                    <span>Post-Deployment Health Checks</span>
                  </h3>
                  <span className="text-xs text-slate-400">{healthChecks.length} checks executed</span>
                </div>

                {healthChecks.length === 0 ? (
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800/80 text-xs text-slate-400 text-center">
                    Health verification pending or in progress...
                  </div>
                ) : (
                  <div className="space-y-2">
                    {healthChecks.map((hc) => (
                      <div
                        key={hc.id}
                        className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between text-xs"
                      >
                        <div className="flex items-center gap-2.5">
                          {hc.status === 'passed' ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                          ) : (
                            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                          )}
                          <div>
                            <div className="font-semibold text-white capitalize">
                              {hc.check_type.replace('_', ' ')}
                            </div>
                            <div className="text-[11px] text-slate-400 font-mono">
                              Latency: {hc.latency_ms}ms • Status: HTTP {hc.status_code || 200}
                            </div>
                          </div>
                        </div>
                        <StatusBadge status={hc.status} size="sm" />
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Streaming Logs Terminal */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                    <Terminal className="w-4 h-4 text-emerald-400" />
                    <span>Deployment Orchestrator Console</span>
                  </h3>
                  <span className="text-[11px] text-slate-400 font-mono">{selectedDep.logs?.length || 0} log entries</span>
                </div>

                <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 max-h-72 overflow-y-auto font-mono text-xs text-slate-300 space-y-1">
                  {selectedDep.logs && selectedDep.logs.length > 0 ? (
                    selectedDep.logs.map((log, idx) => (
                      <div key={idx} className="flex gap-2">
                        <span className="text-slate-600 select-none">
                          {new Date(log.timestamp).toLocaleTimeString()}
                        </span>
                        <span
                          className={`font-semibold ${
                            log.level === 'ERROR'
                              ? 'text-rose-400'
                              : log.level === 'WARN'
                              ? 'text-amber-400'
                              : 'text-emerald-400'
                          }`}
                        >
                          [{log.level}]
                        </span>
                        <span className="text-slate-200">{log.message}</span>
                      </div>
                    ))
                  ) : (
                    <div className="text-slate-500 italic">No logs generated yet.</div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="p-12 text-center glass-card rounded-2xl text-slate-400">
              Select a deployment from the left to inspect logs and health status.
            </div>
          )}
        </div>
      </div>

      {/* Rollback Modal */}
      <RollbackModal
        isOpen={showRollbackModal}
        onClose={() => setShowRollbackModal(false)}
        deployment={selectedDep}
        onRollbackCompleted={() => {
          loadAll();
          if (selectedDep) loadDeploymentDetails(selectedDep.id);
        }}
      />
    </div>
  );
};
