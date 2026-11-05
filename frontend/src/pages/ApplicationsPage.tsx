import React, { useState, useEffect } from 'react';
import api from '../api/client';
import { Project, Environment, Release } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { Layers, Plus, GitBranch, ShieldAlert, Rocket, Server, Check, X, ShieldCheck, Trash2 } from 'lucide-react';
import { ScanReportModal } from '../components/ScanReportModal';

interface ApplicationsPageProps {
  onOpenDeployModal: (project: Project) => void;
}

export const ApplicationsPage: React.FC<ApplicationsPageProps> = ({ onOpenDeployModal }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [releases, setReleases] = useState<Release[]>([]);
  const [loading, setLoading] = useState(true);

  // Modals state
  const [showCreateApp, setShowCreateApp] = useState(false);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [showCreateRelease, setShowCreateRelease] = useState(false);
  const [selectedScanRelease, setSelectedScanRelease] = useState<Release | null>(null);
  const [namespaceEdits, setNamespaceEdits] = useState<Record<string, string>>({});

  // New App Form State
  const [newAppName, setNewAppName] = useState('');
  const [newAppDesc, setNewAppDesc] = useState('');
  const [newAppGit, setNewAppGit] = useState('');
  const [newAppImage, setNewAppImage] = useState('');
  const [newAppPort, setNewAppPort] = useState(3000);
  const [newAppHealth, setNewAppHealth] = useState('/healthz');

  // New Release Form State
  const [newRelVersion, setNewRelVersion] = useState('');
  const [newRelCommit, setNewRelCommit] = useState('');
  const [newRelTag, setNewRelTag] = useState('');

  const loadProjects = async () => {
    try {
      const res = await api.get('/projects');
      setProjects(res.data.data);
      if (res.data.data.length > 0 && !selectedProject) {
        setSelectedProject(res.data.data[0]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadProjectDetails = async (projId: string) => {
    try {
      const [envRes, relRes] = await Promise.all([
        api.get(`/projects/${projId}/environments`),
        api.get(`/projects/${projId}/releases`)
      ]);
      setEnvironments(envRes.data.data);
      setReleases(relRes.data.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  useEffect(() => {
    if (selectedProject) {
      loadProjectDetails(selectedProject.id);
    }
  }, [selectedProject]);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingProjectId) {
        const res = await api.put(`/projects/${editingProjectId}`, {
          description: newAppDesc,
          git_repo: newAppGit,
          image_repository: newAppImage,
          default_port: Number(newAppPort),
          health_path: newAppHealth
        });
        const updated = res.data.data as Project;
        setProjects((current) => current.map((project) => project.id === updated.id ? updated : project));
        setSelectedProject(updated);
        setEditingProjectId(null);
        setShowCreateApp(false);
        return;
      }
      const res = await api.post('/projects', {
        name: newAppName,
        description: newAppDesc,
        git_repo: newAppGit,
        image_repository: newAppImage,
        default_port: Number(newAppPort),
        health_path: newAppHealth
      });
      const created = res.data.data;
      // Auto-create dev and prod environments
      await api.post(`/projects/${created.id}/environments`, {
        name: 'staging',
        k8s_namespace: `${created.name}-staging`,
        replicas: 2,
        deployment_strategy: 'rolling',
        auto_rollback_enabled: true
      });
      await api.post(`/projects/${created.id}/environments`, {
        name: 'production',
        k8s_namespace: `${created.name}-prod`,
        replicas: 3,
        deployment_strategy: 'rolling',
        auto_rollback_enabled: true
      });
      setShowCreateApp(false);
      await loadProjects();
      setSelectedProject(created);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to create application');
    }
  };

  const handleCreateRelease = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProject) return;
    try {
      await api.post(`/projects/${selectedProject.id}/releases`, {
        version: newRelVersion,
        git_commit: newRelCommit,
        image_tag: newRelTag,
        commit_message: `Release ${newRelVersion} build`
      });
      setShowCreateRelease(false);
      loadProjectDetails(selectedProject.id);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to register release');
    }
  };

  const triggerScan = async (relId: string) => {
    if (!selectedProject) return;
    try {
      const res = await api.post(`/projects/${selectedProject.id}/releases/${relId}/scan`);
      await loadProjectDetails(selectedProject.id);
      // open modal with updated release
      const updatedRel = releases.find((r) => r.id === relId);
      if (updatedRel) {
        setSelectedScanRelease({ ...updatedRel, scan_results: res.data.data });
      }
    } catch (err) {
      console.error(err);
    }
  };

  const deleteApplication = async () => {
    if (!selectedProject) return;
    if (!window.confirm(`Delete application "${selectedProject.name}" and all its environments, releases, and deployment history? This cannot be undone.`)) return;
    try {
      await api.delete(`/projects/${selectedProject.id}`);
      const remaining = projects.filter((project) => project.id !== selectedProject.id);
      setProjects(remaining);
      setSelectedProject(remaining[0] || null);
      setEnvironments([]);
      setReleases([]);
    } catch (err: any) {
      window.alert(err.response?.data?.detail || 'Unable to delete application.');
    }
  };

  const updateNamespace = async (environment: Environment) => {
    const namespace = namespaceEdits[environment.id]?.trim();
    if (!namespace || namespace === environment.k8s_namespace) return;
    try {
      const response = await api.put(`/projects/${selectedProject?.id}/environments/${environment.id}`, {
        k8s_namespace: namespace,
      });
      setEnvironments((current) => current.map((item) => item.id === environment.id ? response.data.data : item));
      setNamespaceEdits((current) => ({ ...current, [environment.id]: '' }));
    } catch (err: any) {
      window.alert(err.response?.data?.detail || 'Unable to update Kubernetes namespace.');
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">Applications Registry</h1>
          <p className="text-sm text-slate-400">
            Configure multi-tenant microservices, release artifacts, and deployment environments.
          </p>
        </div>
        <button
          onClick={() => {
            setEditingProjectId(null);
            setNewAppName('');
            setNewAppDesc('');
            setNewAppGit('');
            setNewAppImage('');
            setNewAppPort(3000);
            setNewAppHealth('/healthz');
            setShowCreateApp(true);
          }}
          className="px-4 py-2.5 rounded-xl text-sm font-bold bg-emerald-500 hover:bg-emerald-400 text-slate-950 flex items-center gap-2 self-start sm:self-auto shadow-lg shadow-emerald-500/20 transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>New Application</span>
        </button>
      </div>

      {/* Projects selection chips */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        {projects.map((proj) => (
          <button
            key={proj.id}
            onClick={() => setSelectedProject(proj)}
            className={`px-4 py-2 rounded-xl text-sm font-semibold whitespace-nowrap transition-all ${
              selectedProject?.id === proj.id
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/40 shadow-sm'
                : 'glass-card text-slate-400 hover:text-white'
            }`}
          >
            {proj.name}
          </button>
        ))}
      </div>

      {selectedProject && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Project Details Panel */}
          <div className="space-y-6">
            <div className="p-6 rounded-2xl glass-card space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-extrabold text-lg text-white">{selectedProject.name}</h3>
                <button
                  onClick={() => onOpenDeployModal(selectedProject)}
                  className="px-3 py-1.5 rounded-lg text-xs font-bold bg-emerald-500 text-slate-950 hover:bg-emerald-400 transition-colors flex items-center gap-1.5"
                >
                  <Rocket className="w-3.5 h-3.5" />
                  <span>Deploy</span>
                </button>
                <button
                  onClick={() => {
                    setEditingProjectId(selectedProject.id);
                    setNewAppDesc(selectedProject.description || '');
                    setNewAppGit(selectedProject.git_repo);
                    setNewAppImage(selectedProject.image_repository);
                    setNewAppPort(selectedProject.default_port);
                    setNewAppHealth(selectedProject.health_path);
                    setShowCreateApp(true);
                  }}
                  className="px-3 py-1.5 rounded-lg text-xs font-bold border border-slate-700 text-slate-300 hover:text-white hover:border-slate-500 transition-colors"
                >
                  Edit
                </button>
                <button
                  onClick={() => void deleteApplication()}
                  className="px-3 py-1.5 rounded-lg text-xs font-bold border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 transition-colors flex items-center gap-1.5"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Delete
                </button>
              </div>
              <p className="text-xs text-slate-400">{selectedProject.description || 'No description provided.'}</p>

              <div className="space-y-2 text-xs pt-2 border-t border-slate-800">
                <div className="flex justify-between">
                  <span className="text-slate-400">Git Repository:</span>
                  <a href={selectedProject.git_repo} target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline font-mono">
                    {selectedProject.git_repo.replace('https://', '')}
                  </a>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Image Registry:</span>
                  <span className="text-slate-200 font-mono">{selectedProject.image_repository}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Port / Path:</span>
                  <span className="text-slate-200 font-mono">{selectedProject.default_port} {selectedProject.health_path}</span>
                </div>
              </div>
            </div>

            {/* Environments Card */}
            <div className="p-6 rounded-2xl glass-card space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="font-bold text-sm text-white">Target Environments</h4>
                <span className="text-xs text-slate-400">{environments.length} active</span>
              </div>

              <div className="space-y-3">
                {environments.map((env) => (
                  <div key={env.id} className="p-3.5 bg-slate-950/80 border border-slate-800/80 rounded-xl space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs uppercase text-emerald-400 tracking-wider">{env.name}</span>
                      <div className="flex items-center gap-1">
                        <input
                          aria-label={`${env.name} Kubernetes namespace`}
                          value={namespaceEdits[env.id] ?? env.k8s_namespace}
                          onChange={(event) => setNamespaceEdits((current) => ({
                            ...current,
                            [env.id]: event.target.value,
                          }))}
                          className="w-36 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-[11px] font-mono text-slate-300"
                        />
                        <button
                          onClick={() => void updateNamespace(env)}
                          className="text-[11px] text-emerald-400 hover:text-emerald-300"
                        >
                          Save
                        </button>
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span>Replicas: <strong className="text-white">{env.replicas}</strong></span>
                      <span>Strategy: <strong className="text-white capitalize">{env.deployment_strategy}</strong></span>
                      <span className="text-emerald-400 text-[11px] font-semibold">Auto-Rollback ON</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Releases List & Trivy Scan Integration */}
          <div className="lg:col-span-2 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-base text-white">Release Catalog & Artifacts</h3>
                <p className="text-xs text-slate-400">Immutable versions scanned by Trivy before deployment</p>
              </div>
              <button
                onClick={() => setShowCreateRelease(true)}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-white flex items-center gap-1.5 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Register Release</span>
              </button>
            </div>

            <div className="space-y-3">
              {releases.length === 0 ? (
                <div className="p-8 text-center glass-card rounded-2xl text-slate-400 text-sm">
                  No releases registered yet for this microservice.
                </div>
              ) : (
                releases.map((rel) => (
                  <div key={rel.id} className="p-4 rounded-xl glass-card glass-card-hover space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="font-extrabold text-sm text-white font-mono bg-slate-800 px-2.5 py-1 rounded-lg">
                          {rel.version}
                        </div>
                        <div>
                          <div className="text-xs text-slate-300 font-mono">
                            {rel.image_tag} • git:{rel.git_commit.substring(0, 7)}
                          </div>
                          <div className="text-[11px] text-slate-500 font-mono mt-0.5">
                            {rel.image_reference || `${selectedProject.image_repository}:${rel.image_tag}`}
                          </div>
                          {rel.commit_message && (
                            <div className="text-xs text-slate-400 mt-0.5">{rel.commit_message}</div>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <StatusBadge status={rel.scan_status} />
                        <button
                          onClick={() => triggerScan(rel.id)}
                          className="px-2.5 py-1 rounded-lg text-xs font-medium bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/20 transition-colors flex items-center gap-1"
                        >
                          <ShieldCheck className="w-3.5 h-3.5" />
                          <span>Scan</span>
                        </button>
                        <button
                          onClick={() => setSelectedScanRelease(rel)}
                          className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 hover:text-white transition-colors"
                        >
                          Report
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal: New Application */}
      {showCreateApp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-bold text-lg text-white">
                {editingProjectId ? 'Edit Application Configuration' : 'Register New Application'}
              </h3>
              <button onClick={() => setShowCreateApp(false)} className="p-1 rounded-lg text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleCreateProject} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Application Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. inventory-service"
                  value={newAppName}
                  disabled={!!editingProjectId}
                  onChange={(e) => setNewAppName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Description</label>
                <input
                  type="text"
                  placeholder="Brief summary of service"
                  value={newAppDesc}
                  onChange={(e) => setNewAppDesc(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Git Repository URL *</label>
                <input
                  type="text"
                  required
                  placeholder="https://github.com/org/repo.git"
                  value={newAppGit}
                  onChange={(e) => setNewAppGit(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Image Repository *</label>
                <input
                  type="text"
                  required
                  placeholder="docker.io/org/image-name"
                  value={newAppImage}
                  onChange={(e) => setNewAppImage(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Default Port</label>
                  <input
                    type="number"
                    value={newAppPort}
                    onChange={(e) => setNewAppPort(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Health Path</label>
                  <input
                    type="text"
                    value={newAppHealth}
                    onChange={(e) => setNewAppHealth(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>
              <div className="pt-2 flex justify-end gap-3">
                <button type="button" onClick={() => setShowCreateApp(false)} className="px-4 py-2 text-sm text-slate-400 hover:text-white">
                  Cancel
                </button>
                <button type="submit" className="px-5 py-2 rounded-xl text-sm font-bold bg-emerald-500 text-slate-950 hover:bg-emerald-400">
                {editingProjectId ? 'Save Configuration' : 'Save Application'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: New Release */}
      {showCreateRelease && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-bold text-lg text-white">Register Release Version</h3>
              <button onClick={() => setShowCreateRelease(false)} className="p-1 rounded-lg text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleCreateRelease} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Version (Semver) *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. v1.3.0"
                  value={newRelVersion}
                  onChange={(e) => setNewRelVersion(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Git Commit SHA *</label>
                <input
                  type="text"
                  required
                  placeholder="40-char git commit SHA"
                  value={newRelCommit}
                  onChange={(e) => setNewRelCommit(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Docker Image Tag *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. v1.3.0"
                  value={newRelTag}
                  onChange={(e) => setNewRelTag(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div className="pt-2 flex justify-end gap-3">
                <button type="button" onClick={() => setShowCreateRelease(false)} className="px-4 py-2 text-sm text-slate-400 hover:text-white">
                  Cancel
                </button>
                <button type="submit" className="px-5 py-2 rounded-xl text-sm font-bold bg-emerald-500 text-slate-950 hover:bg-emerald-400">
                  Register
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Trivy Scan Report Modal */}
      <ScanReportModal
        isOpen={!!selectedScanRelease}
        onClose={() => setSelectedScanRelease(null)}
        release={selectedScanRelease}
      />
    </div>
  );
};
