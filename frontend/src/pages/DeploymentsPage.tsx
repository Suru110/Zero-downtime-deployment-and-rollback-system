import React, { useState, useEffect, useRef } from 'react';
import api from '../api/client';
import { Deployment, Project, Environment, Release, HealthCheck } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { GitBranch, RotateCcw, Terminal, Activity, CheckCircle2, AlertTriangle, Cpu, Layers, Trash2, ExternalLink, Pause, Play, Rocket, Clipboard, Loader2 } from 'lucide-react';
import { RollbackModal } from '../components/RollbackModal';
import { resolvePublicUrl } from '../utils/publicUrl';

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
  const [endpointLoading, setEndpointLoading] = useState(false);
  const selectedIdRef = useRef<string | null>(null);
  const endpointRevisionRef = useRef(new Map<string, number>());
  const endpointSequenceRef = useRef(0);
  const endpointCheckAtRef = useRef(new Map<string, number>());
  const endpointRequestsRef = useRef(new Map<string, Promise<Deployment>>());

  const mergeDeployment = (
    current: Deployment,
    incoming: Deployment,
    preserveCurrentEndpoint: boolean,
  ): Deployment => {
    const currentMetadata = current.metadata_info || {};
    const incomingMetadata = incoming.metadata_info || {};
    const endpointKeys = [
      'endpoint_status',
      'public_url',
      'endpoint_details',
      'endpoint_error',
      'adapter_details',
    ];
    const hasIncomingEndpoint = endpointKeys.some((key) =>
      Object.prototype.hasOwnProperty.call(incomingMetadata, key),
    );
    const preserveEndpoint = preserveCurrentEndpoint || !hasIncomingEndpoint;
    const metadata = { ...currentMetadata, ...incomingMetadata };

    if (preserveEndpoint) {
      endpointKeys.forEach((key) => {
        if (Object.prototype.hasOwnProperty.call(currentMetadata, key)) {
          metadata[key] = currentMetadata[key];
        } else {
          delete metadata[key];
        }
      });
    }

    return { ...current, ...incoming, metadata_info: metadata };
  };

  const applyDeploymentUpdate = (
    incoming: Deployment,
    requestSequence: number,
    fromEndpoint: boolean,
  ) => {
    if (fromEndpoint) {
      endpointSequenceRef.current += 1;
      endpointRevisionRef.current.set(
        incoming.id,
        endpointSequenceRef.current,
      );
    }
    const preserveCurrentEndpoint =
      (endpointRevisionRef.current.get(incoming.id) || 0) > requestSequence &&
      !fromEndpoint;
    setDeployments((current) =>
      current.map((item) =>
        item.id === incoming.id
          ? mergeDeployment(item, incoming, preserveCurrentEndpoint)
          : item,
      ),
    );
    setSelectedDep((current) => {
      if (current?.id !== incoming.id && selectedIdRef.current !== incoming.id) {
        return current;
      }
      const selected = current?.id === incoming.id ? current : incoming;
      return mergeDeployment(selected, incoming, preserveCurrentEndpoint);
    });
  };

  const requestEndpoint = (deploymentId: string): Promise<Deployment> => {
    const pending = endpointRequestsRef.current.get(deploymentId);
    if (pending) return pending;

    const requestSequence = endpointSequenceRef.current;
    endpointCheckAtRef.current.set(deploymentId, Date.now());
    const request = api
      .get(`/deployments/${deploymentId}/endpoint`)
      .then((response) => {
        const updated = response.data.data as Deployment;
        applyDeploymentUpdate(updated, requestSequence, true);
        return updated;
      })
      .finally(() => {
        endpointRequestsRef.current.delete(deploymentId);
      });
    endpointRequestsRef.current.set(deploymentId, request);
    return request;
  };

  const loadAll = async () => {
    const requestSequence = endpointSequenceRef.current;
    try {
      const [depRes, projRes] = await Promise.all([
        api.get('/deployments?limit=50'),
        api.get('/projects')
      ]);
      const fresh = depRes.data.data as Deployment[];
      setDeployments((current) =>
        fresh.map((deployment) => {
          const existing = current.find((item) => item.id === deployment.id);
          const preserveEndpoint =
            (endpointRevisionRef.current.get(deployment.id) || 0) >
            requestSequence;
          return existing
            ? mergeDeployment(existing, deployment, preserveEndpoint)
            : deployment;
        }),
      );
      setProjects(projRes.data.data);

      if (fresh.length > 0) {
        const selected =
          fresh.find((deployment) => deployment.id === initialSelectedId) ||
          fresh.find((deployment) => deployment.id === selectedIdRef.current) ||
          fresh[0];
        selectedIdRef.current = selected.id;
        setSelectedDep((current) => {
          const existing = current?.id === selected.id ? current : selected;
          return mergeDeployment(
            existing,
            selected,
            (endpointRevisionRef.current.get(selected.id) || 0) >
              requestSequence,
          );
        });
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadDeploymentDetails = async (depId: string) => {
    const requestSequence = endpointSequenceRef.current;
    try {
      const [depRes, hcRes] = await Promise.all([
        api.get(`/deployments/${depId}`),
        api.get(`/deployments/${depId}/health-checks`)
      ]);
      const deployment = depRes.data.data as Deployment;
      applyDeploymentUpdate(deployment, requestSequence, false);
      setHealthChecks(hcRes.data.data);
      if (
        ['active', 'deploying', 'verifying'].includes(deployment.status) &&
        (!getPublicUrl(deployment) ||
          deployment.metadata_info?.endpoint_status !== 'ready')
      ) {
        if (selectedIdRef.current === depId) setEndpointLoading(true);
        try {
          await requestEndpoint(depId);
        } catch (err) {
          console.error('Failed to discover deployment endpoint:', err);
        } finally {
          if (selectedIdRef.current === depId) setEndpointLoading(false);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  /**
   * Background endpoint poller — runs independently of which deployment is
   * selected. For every active/deploying/verifying deployment that doesn't yet
   * have a ready public URL it calls the /endpoint route so the URL is
   * discovered and persisted even before the user clicks on the card.
   */
  const refreshPendingEndpoints = async (current: Deployment[]) => {
    const now = Date.now();
    const needsEndpoint = current.filter((deployment) => {
      if (!['active', 'deploying', 'verifying'].includes(deployment.status)) {
        return false;
      }
      if (endpointRequestsRef.current.has(deployment.id)) return false;

      const publicUrl = getPublicUrl(deployment);
      const metadata = deployment.metadata_info || {};
      const endpointDetails = metadata.endpoint_details || {};
      const lastCheck = endpointCheckAtRef.current.get(deployment.id) || 0;
      const isQuickTunnel =
        endpointDetails.tunnel_provider === 'cloudflare-quick-tunnel' ||
        (!!publicUrl &&
          new URL(publicUrl).hostname.toLowerCase().endsWith('.trycloudflare.com'));
      if (metadata.endpoint_status === 'unavailable') return false;
      if (metadata.endpoint_status === 'error') {
        return now - lastCheck >= 30000;
      }
      if (
        publicUrl &&
        metadata.endpoint_status === 'ready' &&
        (!isQuickTunnel ||
          now - lastCheck < 30000)
      ) {
        return false;
      }
      return true;
    });
    await Promise.allSettled(
      needsEndpoint.map(async (deployment) => {
        try {
          await requestEndpoint(deployment.id);
        } catch (err) {
          console.error('Background endpoint discovery failed:', err);
        }
      }),
    );
  };

  useEffect(() => {
    loadAll();
    const interval = setInterval(async () => {
      const requestSequence = endpointSequenceRef.current;
      try {
        const [depRes] = await Promise.all([api.get('/deployments?limit=50')]);
        const fresh: Deployment[] = depRes.data.data;
        setDeployments((current) =>
          fresh.map((deployment) => {
            const existing = current.find((item) => item.id === deployment.id);
            if (!existing) return deployment;
            const preserveEndpoint =
              (endpointRevisionRef.current.get(deployment.id) || 0) >
              requestSequence;
            return mergeDeployment(existing, deployment, preserveEndpoint);
          }),
        );
        // Refresh health checks for the selected deployment
        const selectedId = selectedIdRef.current;
        if (selectedId) {
          try {
            const hcRes = await api.get(`/deployments/${selectedId}/health-checks`);
            setHealthChecks(hcRes.data.data);
            const match = fresh.find((deployment) => deployment.id === selectedId);
            if (match) applyDeploymentUpdate(match, requestSequence, false);
          } catch {
            // ignore
          }
        }
        // Discover public URLs for any deployment that doesn't have one yet
        await refreshPendingEndpoints(fresh);
      } catch (err) {
        console.error(err);
      }
    }, 4000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDep?.id]);

  const filteredDeployments = deployments.filter((d) => {
    if (filter === 'all') return true;
    return d.status === filter;
  });

  const getProjectName = (projId: string) => projects.find((p) => p.id === projId)?.name || projId;

  const getPublicUrl = (deployment: Deployment): string | undefined =>
    resolvePublicUrl(deployment.metadata_info);

  const getEndpointStatusLabel = (deployment: Deployment): string => {
    const metadata = deployment.metadata_info || {};
    if (getPublicUrl(deployment)) return 'Public endpoint ready';

    const error = String(metadata.endpoint_error || '').toLowerCase();
    if (error.includes('port-forward')) return 'Port-forward failed';
    if (error.includes('cloudflared') || error.includes('quick tunnel')) {
      return 'Cloudflare tunnel failed';
    }
    if (
      error.includes('public endpoint') ||
      error.includes('health check') ||
      error.includes('dns resolution')
    ) {
      return 'Verifying public endpoint failed';
    }
    if (metadata.endpoint_status === 'error' || metadata.endpoint_phase === 'failed') {
      return 'Endpoint failed';
    }
    return 'Waiting for Kubernetes service readiness';
  };

  const refreshEndpoint = async (deployment: Deployment) => {
    const isSelected = selectedIdRef.current === deployment.id;
    if (isSelected) setEndpointLoading(true);
    try {
      await requestEndpoint(deployment.id);
    } catch (err) {
      console.error('Failed to refresh deployment endpoint:', err);
      const errorMetadata: Deployment['metadata_info'] = {
        ...(deployment.metadata_info || {}),
        endpoint_status: 'error',
        endpoint_phase: 'failed',
        endpoint_error: 'Endpoint refresh request failed.',
      };
      delete errorMetadata.public_url;
      setDeployments((current) =>
        current.map((item) =>
          item.id === deployment.id
            ? { ...item, metadata_info: errorMetadata }
            : item,
        ),
      );
      setSelectedDep((current) =>
        current?.id === deployment.id
          ? { ...current, metadata_info: errorMetadata }
          : current,
      );
    } finally {
      if (isSelected) setEndpointLoading(false);
    }
  };

  const copyPublicUrl = async (deployment: Deployment) => {
    const publicUrl = getPublicUrl(deployment);
    if (!publicUrl) return;
    try {
      await navigator.clipboard.writeText(publicUrl);
      window.alert('Application URL copied.');
    } catch (err) {
      console.error('Failed to copy application URL:', err);
      window.alert('Unable to copy the application URL.');
    }
  };

  const deleteDeployment = async (deployment: Deployment) => {
    if (!window.confirm(`Delete deployment ${deployment.id.slice(0, 8)}? This cannot be undone.`)) return;
    try {
      await api.delete(`/deployments/${deployment.id}`);
      setDeployments((current) => current.filter((item) => item.id !== deployment.id));
      if (selectedDep?.id === deployment.id) {
        selectedIdRef.current = null;
        setSelectedDep(null);
      }
    } catch (err: any) {
      window.alert(err.response?.data?.detail || 'Unable to delete deployment.');
    }
  };

  const deleteAllDeployments = async () => {
    if (!window.confirm('Delete all completed deployment records? This cannot be undone.')) return;
    try {
      await api.delete('/deployments');
      setDeployments([]);
      selectedIdRef.current = null;
      setSelectedDep(null);
    } catch (err: any) {
      window.alert(err.response?.data?.detail || 'Unable to delete deployment history.');
    }
  };

  const togglePause = async (deployment: Deployment) => {
    const paused = deployment.metadata_info?.paused === true;
    const requestSequence = endpointSequenceRef.current;
    try {
      const response = await api.post(`/deployments/${deployment.id}/${paused ? 'resume' : 'pause'}`);
      const updated = response.data.data as Deployment;
      applyDeploymentUpdate(updated, requestSequence, false);
    } catch (err: any) {
      window.alert(err.response?.data?.detail || `Unable to ${paused ? 'resume' : 'pause'} deployment.`);
    }
  };

  const redeploy = async (deployment: Deployment) => {
    if (!window.confirm('Redeploy this release to the same environment?')) return;
    try {
      await api.post('/deployments', {
        project_id: deployment.project_id,
        environment_id: deployment.environment_id,
        release_id: deployment.release_id,
        override_strategy: deployment.strategy,
        redeploy: true,
        simulate_failure: false,
      });
      window.alert('Redeployment started.');
      await loadAll();
    } catch (err: any) {
      window.alert(err.response?.data?.detail || 'Unable to start redeployment.');
    }
  };

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
          <button
            onClick={() => void deleteAllDeployments()}
            className="ml-1 px-3 py-1.5 rounded-lg text-xs font-semibold text-rose-400 hover:bg-rose-500/10 whitespace-nowrap"
          >
            Delete All
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Deployment List */}
        <div className="lg:col-span-5 space-y-3">
          {filteredDeployments.map((dep) => (
            <div
              key={dep.id}
              onClick={() => {
                selectedIdRef.current = dep.id;
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
                <div className="flex items-center gap-2">
                  <StatusBadge status={dep.metadata_info?.paused ? 'paused' : dep.status} size="sm" />
                  {!['active', 'failed', 'rolled_back', 'cancelled'].includes(dep.status) && (
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        void togglePause(dep);
                      }}
                      aria-label={dep.metadata_info?.paused ? 'Resume deployment' : 'Pause deployment'}
                      className="text-slate-500 hover:text-amber-400"
                    >
                      {dep.metadata_info?.paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
                    </button>
                  )}
                  {['pending', 'active', 'failed', 'rolled_back', 'cancelled'].includes(dep.status) && (
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        void deleteDeployment(dep);
                      }}
                      aria-label="Delete deployment"
                      className="text-slate-500 hover:text-rose-400"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between text-xs text-slate-400">
                <span className="capitalize">Strategy: <strong className="text-slate-300">{dep.strategy}</strong></span>
                <span className="font-mono text-[11px] text-slate-400">{new Date(dep.started_at).toLocaleTimeString()}</span>
              </div>

              {getPublicUrl(dep) && (
                <div className="mt-2 flex items-center gap-2">
                  <a
                    href={getPublicUrl(dep)}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(event) => event.stopPropagation()}
                    className="flex min-w-0 flex-1 items-center gap-1.5 truncate text-xs text-emerald-300 hover:text-emerald-200"
                  >
                    <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{getPublicUrl(dep)}</span>
                  </a>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      void copyPublicUrl(dep);
                    }}
                    aria-label="Copy application URL"
                    className="text-slate-400 hover:text-white"
                  >
                    <Clipboard className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
              {dep.status === 'active' && !getPublicUrl(dep) && (
                <div className="mt-2 text-xs text-amber-300">
                  {getEndpointStatusLabel(dep)}
                </div>
              )}

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
                    <StatusBadge status={selectedDep.metadata_info?.paused ? 'paused' : selectedDep.status} />
                  </div>
                  <p className="text-xs text-slate-400 font-mono mt-1">
                    Deployment ID: {selectedDep.id}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2 self-start sm:self-auto">
                  {['failed', 'rolled_back', 'cancelled'].includes(selectedDep.status) && (
                    <button
                      onClick={() => void redeploy(selectedDep)}
                      className="px-4 py-2 rounded-xl text-xs font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 transition-all flex items-center gap-2"
                    >
                      <Rocket className="w-3.5 h-3.5" />
                      <span>Redeploy</span>
                    </button>
                  )}
                  {['pending', 'scanning', 'deploying', 'verifying'].includes(selectedDep.status) && (
                    <button
                      onClick={() => void togglePause(selectedDep)}
                      className="px-4 py-2 rounded-xl text-xs font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/25 transition-all flex items-center gap-2"
                    >
                      {selectedDep.metadata_info?.paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
                      <span>{selectedDep.metadata_info?.paused ? 'Resume' : 'Pause'}</span>
                    </button>
                  )}
                  {['active', 'deploying', 'verifying'].includes(selectedDep.status) && (
                    <button
                      onClick={() => setShowRollbackModal(true)}
                      className="px-4 py-2 rounded-xl text-xs font-bold bg-purple-500/15 text-purple-300 border border-purple-500/30 hover:bg-purple-500/25 transition-all flex items-center gap-2 shadow-sm"
                    >
                      <RotateCcw className="w-3.5 h-3.5 text-purple-400" />
                      <span>Trigger Rollback</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Execution Info & Adapter Spec */}
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
                {endpointLoading ? (
                  <div className="flex items-center gap-2 text-sm text-amber-300">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Checking Kubernetes readiness and public endpoint...
                  </div>
                ) : getPublicUrl(selectedDep) ? (
                  <div className="space-y-2">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <span className="truncate font-mono text-xs text-emerald-300">
                        {getPublicUrl(selectedDep)}
                      </span>
                      <div className="flex shrink-0 gap-2">
                        <button
                          type="button"
                          onClick={() => void refreshEndpoint(selectedDep)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 px-3 py-1.5 text-xs font-bold text-emerald-200 hover:bg-emerald-500/20"
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                          Refresh Endpoint
                        </button>
                        <a
                          href={getPublicUrl(selectedDep)}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/20 px-3 py-1.5 text-xs font-bold text-emerald-200 hover:bg-emerald-500/30"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          Open Application
                        </a>
                        <button
                          type="button"
                          onClick={() => void copyPublicUrl(selectedDep)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 px-3 py-1.5 text-xs font-bold text-emerald-200 hover:bg-emerald-500/20"
                        >
                          <Clipboard className="h-3.5 w-3.5" />
                          Copy URL
                        </button>
                      </div>
                    </div>
                    {selectedDep.metadata_info?.endpoint_details?.tunnel_provider ===
                      'cloudflare-quick-tunnel' && (
                      <p className="text-[11px] text-slate-400">
                        Quick Tunnel URLs change when a tunnel is recreated.
                      </p>
                    )}
                    {selectedDep.metadata_info?.last_verified_at && (
                      <p className="text-[11px] text-slate-400">
                        Last verified:{' '}
                        {new Date(
                          selectedDep.metadata_info.last_verified_at,
                        ).toLocaleString()}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="text-sm text-amber-300">
                    <div className="font-semibold">
                      {getEndpointStatusLabel(selectedDep)}
                    </div>
                    <div className="mt-1 text-xs text-slate-400">
                      {selectedDep.metadata_info?.endpoint_error ||
                        'Kubernetes has not assigned a reachable endpoint yet.'}
                    </div>
                    <button
                      type="button"
                      onClick={() => void refreshEndpoint(selectedDep)}
                      disabled={endpointLoading}
                      className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-amber-500/30 px-3 py-1.5 text-xs font-bold text-amber-200 hover:bg-amber-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      Retry Endpoint
                    </button>
                  </div>
                )}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl">
                  <div className="text-[11px] text-slate-400 uppercase font-semibold">Namespace</div>
                  <div className="text-sm font-bold text-white">
                    {selectedDep.metadata_info?.namespace ||
                      selectedDep.metadata_info?.endpoint_details?.namespace ||
                      '—'}
                  </div>
                </div>
                <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl">
                  <div className="text-[11px] text-slate-400 uppercase font-semibold">Kubernetes Service</div>
                  <div className="text-sm font-bold text-white">
                    {selectedDep.metadata_info?.service_name ||
                      selectedDep.metadata_info?.endpoint_details?.service_name ||
                      '—'}
                  </div>
                </div>
                <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl">
                  <div className="text-[11px] text-slate-400 uppercase font-semibold">Endpoint Status</div>
                  <div className="text-sm font-bold text-white">
                    {getEndpointStatusLabel(selectedDep)}
                  </div>
                </div>
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
