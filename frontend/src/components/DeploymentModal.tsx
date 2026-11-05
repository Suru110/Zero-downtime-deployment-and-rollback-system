import React, { useEffect, useMemo, useState } from 'react';
import { Project, Environment, Release } from '../types';
import api from '../api/client';
import { X, Rocket, AlertTriangle, ShieldCheck, CheckCircle } from 'lucide-react';

interface DeploymentModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project;
  environments: Environment[];
  releases: Release[];
  onReleaseCreated: (release: Release) => void;
  onDeploymentTriggered: () => void;
}

export const DeploymentModal: React.FC<DeploymentModalProps> = ({
  isOpen,
  onClose,
  project,
  environments,
  releases,
  onDeploymentTriggered,
  onReleaseCreated
}) => {
  const [selectedEnvId, setSelectedEnvId] = useState('');
  const [selectedRelId, setSelectedRelId] = useState('');
  const [strategy, setStrategy] = useState<'rolling' | 'canary'>('rolling');
  const [simulateFailure, setSimulateFailure] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creatingRelease, setCreatingRelease] = useState(false);
  const [releaseVersion, setReleaseVersion] = useState('');
  const [releaseTag, setReleaseTag] = useState('');
  const [releaseCommit, setReleaseCommit] = useState('');
  const [availableEnvironments, setAvailableEnvironments] = useState<Environment[]>(environments);
  const [availableReleases, setAvailableReleases] = useState<Release[]>(releases);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [creatingEnvironment, setCreatingEnvironment] = useState(false);

  const deployableReleases = useMemo(
    () => availableReleases.filter((release) => release.build_status === 'published' || !release.build_status),
    [availableReleases]
  );

  useEffect(() => {
    if (!isOpen) return;

    setSimulateFailure(false);
    let cancelled = false;
    const loadOptions = async () => {
      setLoadingOptions(true);
      setError(null);
      try {
        const [environmentResponse, releaseResponse] = await Promise.all([
          api.get(`/projects/${project.id}/environments`),
          api.get(`/projects/${project.id}/releases`)
        ]);
        if (!cancelled) {
          setAvailableEnvironments(environmentResponse.data.data);
          setAvailableReleases(releaseResponse.data.data);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(
            err.response?.data?.detail ||
            'Unable to load deployment environments and releases for this application.'
          );
        }
      } finally {
        if (!cancelled) setLoadingOptions(false);
      }
    }
    void loadOptions();
    return () => {
      cancelled = true;
    };
  }, [isOpen, project.id]);

  useEffect(() => {
    setAvailableEnvironments(environments);
  }, [environments]);

  useEffect(() => {
    setAvailableReleases(releases);
  }, [releases]);

  useEffect(() => {
    if (isOpen) {
      setSelectedEnvId((current) =>
        availableEnvironments.some((environment) => environment.id === current)
          ? current
          : availableEnvironments[0]?.id || ''
      );
    }
  }, [availableEnvironments, isOpen]);

  useEffect(() => {
    if (!deployableReleases.some((release) => release.id === selectedRelId)) {
      setSelectedRelId(deployableReleases[0]?.id || '');
    }
  }, [deployableReleases, selectedRelId]);

  const createExistingImageRelease = async () => {
    setCreatingRelease(true);
    setError(null);
    try {
      const response = await api.post(`/projects/${project.id}/releases`, {
        version: releaseVersion,
        git_commit: releaseCommit,
        image_tag: releaseTag,
        image_reference: `${project.image_repository}:${releaseTag}`,
        commit_message: 'Published existing container image'
      });
      const release = response.data.data as Release;
      setAvailableReleases((current) => [release, ...current.filter((item) => item.id !== release.id)]);
      onReleaseCreated(release);
      setSelectedRelId(release.id);
      setReleaseVersion('');
      setReleaseTag('');
      setReleaseCommit('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Unable to create the release.');
    } finally {
      setCreatingRelease(false);
    }
  };

  const createStagingEnvironment = async () => {
    setCreatingEnvironment(true);
    setError(null);
    try {
      const namespace = `${project.name.toLowerCase().replace(/[^a-z0-9-]/g, '-')}-staging`;
      const response = await api.post(`/projects/${project.id}/environments`, {
        name: 'staging',
        k8s_namespace: namespace,
        replicas: 2,
        deployment_strategy: 'rolling',
        auto_rollback_enabled: true
      });
      const environment = response.data.data as Environment;
      setAvailableEnvironments((current) => [environment, ...current]);
      setSelectedEnvId(environment.id);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Unable to create the staging environment.');
    } finally {
      setCreatingEnvironment(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await api.post('/deployments', {
        project_id: project.id,
        environment_id: selectedEnvId,
        release_id: selectedRelId,
        override_strategy: strategy,
        simulate_failure: simulateFailure
      });
      onDeploymentTriggered();
      onClose();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to trigger deployment');
    } finally {
      setLoading(false);
    }
  };

  const selectedRel = releases.find((r) => r.id === selectedRelId);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Rocket className="w-5 h-5 text-emerald-400" />
            <h3 className="font-bold text-lg text-white">Trigger Deployment</h3>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-400 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Application
            </label>
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl text-sm font-semibold text-white">
              {project.name} <span className="text-xs text-slate-400">({project.image_repository})</span>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Target Environment
            </label>
            <select
              value={selectedEnvId}
              onChange={(e) => setSelectedEnvId(e.target.value)}
              disabled={loadingOptions || availableEnvironments.length === 0}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500"
            >
              {loadingOptions && <option value="">Loading environments...</option>}
              {availableEnvironments.map((env) => (
                <option key={env.id} value={env.id}>
                  {env.name.toUpperCase()} — {env.k8s_namespace} ({env.replicas} pods, strategy: {env.deployment_strategy})
                </option>
              ))}
            </select>
            {!loadingOptions && availableEnvironments.length === 0 && (
              <div className="mt-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
                <p>No environments are configured for this application. Create a staging environment before deploying.</p>
                <button
                  type="button"
                  onClick={() => void createStagingEnvironment()}
                  disabled={creatingEnvironment}
                  className="mt-2 rounded-lg bg-amber-400 px-3 py-1.5 font-semibold text-slate-950 disabled:opacity-50"
                >
                  {creatingEnvironment ? 'Creating staging...' : 'Create Staging Environment'}
                </button>
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Release Version
            </label>
            <select
              value={selectedRelId}
              onChange={(e) => setSelectedRelId(e.target.value)}
              disabled={loadingOptions || deployableReleases.length === 0}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500"
            >
              {loadingOptions && <option value="">Loading releases...</option>}
              {deployableReleases.map((rel) => (
                <option key={rel.id} value={rel.id}>
                  {rel.version} (Tag: {rel.image_tag}, SHA: {rel.git_commit.substring(0, 8)})
                </option>
              ))}
            </select>
            {deployableReleases.length === 0 && (
              <div className="mt-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
                No published releases exist for this application. Create a release from an image that has already been published to {project.image_repository}.
                <div className="mt-3 space-y-2">
                  <input required placeholder="Version, e.g. v1.0.0" value={releaseVersion} onChange={(e) => setReleaseVersion(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white" />
                  <input required placeholder="Image tag, e.g. v1.0.0" value={releaseTag} onChange={(e) => setReleaseTag(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white" />
                  <input required minLength={7} maxLength={40} placeholder="Git commit SHA" value={releaseCommit} onChange={(e) => setReleaseCommit(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white" />
                  <button type="button" onClick={() => void createExistingImageRelease()} disabled={creatingRelease} className="w-full rounded-lg bg-emerald-500 px-3 py-2 font-semibold text-slate-950 disabled:opacity-50">
                    {creatingRelease ? 'Creating release...' : 'Create First Release'}
                  </button>
                </div>
              </div>
            )}
            {selectedRel && (
              <div className="mt-2 text-xs text-slate-400 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>Vulnerability scan status: <strong className="text-slate-200 capitalize">{selectedRel.scan_status}</strong></span>
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Deployment Strategy
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setStrategy('rolling')}
                className={`p-3 rounded-xl border text-left transition-all ${
                  strategy === 'rolling'
                    ? 'border-emerald-500 bg-emerald-500/10 text-white'
                    : 'border-slate-800 bg-slate-950 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="font-semibold text-sm">Rolling Update</div>
                <div className="text-xs text-slate-400 mt-0.5">Surge new pods, zero downtime</div>
              </button>

              <button
                type="button"
                onClick={() => setStrategy('canary')}
                className={`p-3 rounded-xl border text-left transition-all ${
                  strategy === 'canary'
                    ? 'border-emerald-500 bg-emerald-500/10 text-white'
                    : 'border-slate-800 bg-slate-950 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="font-semibold text-sm">Canary Rollout</div>
                <div className="text-xs text-slate-400 mt-0.5">10% &rarr; 25% &rarr; 50% &rarr; 100%</div>
              </button>
            </div>
          </div>

          {/* Automated Rollback Simulator Switch */}
          <div className="p-3.5 rounded-xl border border-amber-500/30 bg-amber-500/5 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <span className="text-xs font-semibold text-amber-300">
                  🧪 TEST ONLY: Simulate Health Check Failure
                </span>
              </div>
              <input
                type="checkbox"
                checked={simulateFailure}
                onChange={(e) => setSimulateFailure(e.target.checked)}
                className="w-4 h-4 accent-amber-500 rounded cursor-pointer"
              />
            </div>
            <p className="text-[11px] text-slate-400">
              <strong className="text-amber-300">Leave unchecked for a real deployment.</strong>{' '}
              When checked, this deployment will intentionally fail post-deployment readiness checks
              to verify that the automated rollback engine restores the previous known-good release.
              All errors shown are simulated — the application is never actually deployed.
            </p>
          </div>

          <div className="pt-2 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2.5 rounded-xl text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !selectedRelId || !selectedEnvId}
              className="px-5 py-2.5 rounded-xl text-sm font-bold bg-gradient-to-r from-emerald-600 to-teal-500 text-white hover:from-emerald-500 hover:to-teal-400 shadow-lg shadow-emerald-600/20 disabled:opacity-50 transition-all flex items-center gap-2"
            >
              <Rocket className="w-4 h-4" />
              <span>{loading ? 'Initiating...' : 'Deploy Release'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
