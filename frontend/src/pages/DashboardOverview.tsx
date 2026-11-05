import React, { useEffect, useState, useCallback } from 'react';
import api from '../api/client';
import { SystemStats, Project, Deployment } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { CardSkeleton } from '../components/Skeleton';
import {
  Rocket, RotateCcw, Activity, Clock, CheckCircle2, TrendingUp,
  ArrowRight, RefreshCw, Server, Layers, GitBranch, AlertTriangle
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from 'recharts';

interface DashboardOverviewProps {
  onOpenDeployModal: (project: Project) => void;
  onSelectDeployment: (id: string) => void;
}

interface TrendPoint {
  day: string;
  deployments: number;
  successful: number;
  failed: number;
}

interface PlatformHealth {
  simulation_active: boolean;
  adapter_mode: string;
  simulation_warning: string | null;
  kubernetes: {
    connected: boolean;
    mode: string;
    reason?: string;
    server_version?: string;
  };
}

const STATUS_COLORS: Record<string, string> = {
  active: '#10b981',
  failed: '#f43f5e',
  rolled_back: '#a78bfa',
  deploying: '#60a5fa',
  verifying: '#818cf8',
  pending: '#94a3b8',
  scanning: '#22d3ee',
  cancelled: '#64748b',
};

const KPI_CONFIGS = [
  {
    key: 'total_deployments',
    label: 'Total Deployments',
    icon: Rocket,
    color: 'emerald',
    sub: (s: SystemStats) => `${s.success_rate_pct}% success rate`,
    subIcon: TrendingUp,
  },
  {
    key: 'total_projects',
    label: 'Microservices',
    icon: Layers,
    color: 'cyan',
    sub: (s: SystemStats) => `Across ${s.total_environments} environments`,
    subIcon: Server,
  },
  {
    key: 'rollback_count',
    label: 'Auto Rollbacks',
    icon: RotateCcw,
    color: 'purple',
    sub: () => 'Fail-safe restorations',
    subIcon: CheckCircle2,
  },
  {
    key: 'mttr_minutes',
    label: 'MTTR',
    icon: Clock,
    color: 'amber',
    sub: () => 'Under 3 min SLA target',
    subIcon: TrendingUp,
    suffix: 'm',
  },
];

const COLOR_MAP: Record<string, string> = {
  emerald: 'text-emerald-400',
  cyan: 'text-cyan-400',
  purple: 'text-purple-400',
  amber: 'text-amber-400',
};

const ICON_BG_MAP: Record<string, string> = {
  emerald: 'bg-emerald-500/10 border-emerald-500/20',
  cyan: 'bg-cyan-500/10 border-cyan-500/20',
  purple: 'bg-purple-500/10 border-purple-500/20',
  amber: 'bg-amber-500/10 border-amber-500/20',
};

const AREA_GRADIENT_MAP: Record<string, string> = {
  emerald: '#10b981',
  cyan: '#06b6d4',
  purple: '#a78bfa',
  amber: '#f59e0b',
};

function getStatusDistribution(deployments: Deployment[]) {
  const counts: Record<string, number> = {};
  for (const d of deployments) {
    counts[d.status] = (counts[d.status] || 0) + 1;
  }
  return Object.entries(counts).map(([name, value]) => ({ name, value }));
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload) return null;
  return (
    <div className="glass-card rounded-xl p-3 border border-slate-700/60 text-xs shadow-xl">
      <p className="font-semibold text-white mb-1">{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: <span className="font-bold">{p.value}</span>
        </p>
      ))}
    </div>
  );
};

export const DashboardOverview: React.FC<DashboardOverviewProps> = ({
  onOpenDeployModal,
  onSelectDeployment,
}) => {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [trendData, setTrendData] = useState<TrendPoint[]>([]);
  const [platformHealth, setPlatformHealth] = useState<PlatformHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [statsRes, projRes, depRes, trendRes, healthRes] = await Promise.all([
        api.get('/metrics/system-stats'),
        api.get('/projects'),
        api.get('/deployments?limit=8'),
        api.get('/metrics/deployment-trend').catch(() => ({ data: { data: [] } })),
        api.get('/platform/health').catch(() => ({ data: { data: null } })),
      ]);
      setStats(statsRes.data.data);
      setProjects(projRes.data.data);
      setDeployments(depRes.data.data);
      setTrendData(trendRes.data.data || []);
      setPlatformHealth(healthRes.data.data || null);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(), 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const statusDist = getStatusDistribution(deployments);
  const activeCount = deployments.filter(d => ['deploying', 'verifying', 'scanning', 'pending'].includes(d.status)).length;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Simulation Mode Warning Banner */}
      {platformHealth?.simulation_active && (
        <div className="flex items-start gap-3 px-4 py-3 rounded-xl border border-amber-500/40 bg-amber-500/10 text-amber-300 text-sm">
          <AlertTriangle className="w-5 h-5 mt-0.5 shrink-0 text-amber-400" />
          <div>
            <span className="font-bold text-amber-300">Simulation Mode Active — </span>
            <span className="text-amber-200/80">
              {platformHealth.simulation_warning || 'All adapters are simulated. No real Kubernetes operations are performed.'}
            </span>
            {!platformHealth.kubernetes.connected && platformHealth.kubernetes.reason && (
              <p className="mt-1 text-xs text-amber-200/60">{platformHealth.kubernetes.reason}</p>
            )}
          </div>
        </div>
      )}

      {/* Hero Banner */}
      <div className="relative overflow-hidden rounded-2xl border border-emerald-500/20 shadow-2xl">
        <div className="absolute inset-0 bg-gradient-to-r from-[#021a0f] via-[#0a1628] to-[#0a1628]" />
        <div className="absolute inset-0">
          <div className="absolute top-0 right-0 w-96 h-96 bg-emerald-500/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3" />
          <div className="absolute bottom-0 left-0 w-64 h-64 bg-teal-500/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/4" />
        </div>

        <div className="relative z-10 p-6 md:p-8">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-xs font-semibold text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                Continuous Delivery Engine Online
              </div>
              <h1 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight leading-tight">
                Zero-Downtime Deployment
                <br />
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-teal-300">
                  & Automated Rollback
                </span>
              </h1>
              <p className="text-sm text-slate-400 max-w-xl leading-relaxed">
                ReleasePilot orchestrates Kubernetes rolling updates, canary progression, and instant
                rollback protection against broken releases.
              </p>

              <div className="flex items-center gap-4 text-xs text-slate-400">
                {lastUpdated && (
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    Updated {lastUpdated.toLocaleTimeString()}
                  </span>
                )}
                {activeCount > 0 && (
                  <span className="flex items-center gap-1.5 text-blue-400 font-semibold">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                    {activeCount} deployment{activeCount !== 1 ? 's' : ''} in progress
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center gap-3 shrink-0">
              <button
                onClick={() => fetchData(true)}
                disabled={refreshing}
                className="p-2.5 rounded-xl bg-slate-800/80 text-slate-400 hover:text-white hover:bg-slate-700 border border-slate-700/60 transition-all"
                title="Refresh"
              >
                <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              </button>
              {projects.length > 0 && (
                <button
                  onClick={() => onOpenDeployModal(projects[0])}
                  className="btn-primary flex items-center gap-2 shadow-emerald-600/25"
                  id="hero-deploy-btn"
                >
                  <Rocket className="w-4 h-4" />
                  Deploy Now
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {loading
          ? Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)
          : KPI_CONFIGS.map((cfg) => {
            const Icon = cfg.icon;
            const SubIcon = cfg.subIcon;
            const value = stats ? (stats as any)[cfg.key] : null;
            const colorText = COLOR_MAP[cfg.color];
            const iconBg = ICON_BG_MAP[cfg.color];

            return (
              <div key={cfg.key} className="p-5 rounded-2xl glass-card space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                    {cfg.label}
                  </span>
                  <div className={`w-8 h-8 rounded-lg border flex items-center justify-center ${iconBg}`}>
                    <Icon className={`w-4 h-4 ${colorText}`} />
                  </div>
                </div>

                <div className={`text-3xl font-extrabold ${colorText}`}>
                  {value !== null ? `${value}${cfg.suffix || ''}` : '--'}
                </div>

                {stats && (
                  <div className={`flex items-center gap-1 text-xs ${colorText} opacity-80`}>
                    <SubIcon className="w-3 h-3" />
                    <span>{cfg.sub(stats)}</span>
                  </div>
                )}
              </div>
            );
          })}
      </div>

      {/* Charts + Recent Deployments */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
        {/* Deployment Trend Chart */}
        <div className="xl:col-span-3 glass-card rounded-2xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-white">Deployment Activity</h2>
              <p className="text-xs text-slate-400 mt-0.5">7-day rolling view – real data</p>
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-400">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-0.5 bg-emerald-400 rounded" /> Successful
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-0.5 bg-rose-400 rounded" /> Failed
              </span>
            </div>
          </div>

          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <defs>
                  <linearGradient id="gradSuccess" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradFailed" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(51,65,85,0.4)" vertical={false} />
                <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Area
                  type="monotone"
                  dataKey="successful"
                  stroke="#10b981"
                  strokeWidth={2}
                  fill="url(#gradSuccess)"
                  dot={false}
                  activeDot={{ r: 4, fill: '#10b981' }}
                />
                <Area
                  type="monotone"
                  dataKey="failed"
                  stroke="#f43f5e"
                  strokeWidth={2}
                  fill="url(#gradFailed)"
                  dot={false}
                  activeDot={{ r: 4, fill: '#f43f5e' }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Status Distribution Donut */}
        <div className="xl:col-span-2 glass-card rounded-2xl p-5 space-y-4">
          <div>
            <h2 className="text-sm font-bold text-white">Status Distribution</h2>
            <p className="text-xs text-slate-400 mt-0.5">Last 8 deployments</p>
          </div>

          {deployments.length === 0 ? (
            <div className="flex items-center justify-center h-40 text-slate-500 text-sm">
              No deployments yet
            </div>
          ) : (
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={statusDist}
                    cx="50%"
                    cy="50%"
                    innerRadius={52}
                    outerRadius={78}
                    paddingAngle={3}
                    dataKey="value"
                    strokeWidth={0}
                  >
                    {statusDist.map((entry, index) => (
                      <Cell
                        key={index}
                        fill={STATUS_COLORS[entry.name] || '#64748b'}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                  <Legend
                    formatter={(value) => (
                      <span className="text-xs text-slate-400 capitalize">{value}</span>
                    )}
                    iconType="circle"
                    iconSize={8}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* Applications + Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Registered Applications */}
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-sm font-bold text-white">Registered Applications</h2>
            <span className="text-xs text-slate-500">{projects.length} total</span>
          </div>

          {loading
            ? Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="p-4 rounded-xl glass-card space-y-2 animate-pulse">
                <div className="skeleton h-3 w-32" />
                <div className="skeleton h-2.5 w-48" />
              </div>
            ))
            : projects.length === 0
              ? (
                <div className="p-8 text-center glass-card rounded-2xl text-slate-500 text-sm">
                  <Layers className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  No applications registered yet
                </div>
              )
              : projects.map((proj) => (
                <div
                  key={proj.id}
                  className="p-4 rounded-xl glass-card glass-card-hover space-y-2.5 cursor-default"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                          <Server className="w-3.5 h-3.5 text-emerald-400" />
                        </div>
                        <h3 className="font-bold text-white text-sm truncate">{proj.name}</h3>
                      </div>
                      <p className="text-xs text-slate-500 font-mono mt-1.5 truncate pl-9">
                        {proj.image_repository}
                      </p>
                    </div>
                    <button
                      onClick={() => onOpenDeployModal(proj)}
                      className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20 transition-colors shrink-0"
                      title={`Deploy ${proj.name}`}
                    >
                      <Rocket className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-slate-800/60 text-xs">
                    <span className="flex items-center gap-1.5 text-slate-400">
                      <GitBranch className="w-3 h-3" />
                      {proj.default_branch}
                    </span>
                    <span className="font-mono text-[11px] text-slate-500">
                      :{proj.default_port}
                    </span>
                  </div>
                </div>
              ))}
        </div>

        {/* Deployment Activity Feed */}
        <div className="lg:col-span-3 space-y-3">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-sm font-bold text-white">Deployment Activity Feed</h2>
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Live
            </span>
          </div>

          {loading
            ? Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="p-4 rounded-xl glass-card space-y-2 animate-pulse">
                <div className="flex items-center gap-3">
                  <div className="skeleton h-6 w-24 rounded-full" />
                  <div className="skeleton h-3 w-32" />
                </div>
                <div className="skeleton h-1.5 w-full rounded-full" />
              </div>
            ))
            : deployments.length === 0
              ? (
                <div className="p-10 text-center glass-card rounded-2xl text-slate-500 text-sm">
                  <Rocket className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  No deployments recorded yet. Deploy your first application to get started.
                </div>
              )
              : deployments.map((dep) => {
                const project = projects.find((p) => p.id === dep.project_id);
                const isActive = ['deploying', 'verifying', 'scanning'].includes(dep.status);
                return (
                  <div
                    key={dep.id}
                    id={`dep-${dep.id}`}
                    onClick={() => onSelectDeployment(dep.id)}
                    className="p-4 rounded-xl glass-card glass-card-hover cursor-pointer space-y-2.5 group"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <StatusBadge status={dep.status} />
                        <div className="min-w-0">
                          <div className="font-semibold text-sm text-white truncate">
                            {project?.name ?? dep.project_id}
                          </div>
                          <div className="text-xs text-slate-500 flex items-center gap-2 mt-0.5">
                            <span className="capitalize">{dep.strategy}</span>
                            <span>·</span>
                            <span className="font-mono text-[10px]">{dep.adapter_name}</span>
                            {dep.is_simulated && (
                              <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 text-[10px] font-semibold border border-amber-500/20">
                                SIM
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="text-right shrink-0 flex items-center gap-2">
                        <div>
                          <div className={`text-xs font-bold ${isActive ? 'text-blue-400' : 'text-slate-400'}`}>
                            {dep.progress}%
                          </div>
                          <div className="text-[10px] text-slate-500">
                            {new Date(dep.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </div>
                        </div>
                        <ArrowRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-slate-400 transition-colors" />
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div className="progress-bar">
                      <div
                        className={`progress-bar-fill ${dep.status === 'failed' ? 'bg-rose-500' :
                            dep.status === 'rolled_back' ? 'bg-purple-500' :
                              dep.status === 'active' ? 'bg-emerald-500' :
                                'bg-blue-500'
                          }`}
                        style={{ width: `${dep.progress}%` }}
                      />
                    </div>

                    {/* Latest log line */}
                    {dep.logs && dep.logs.length > 0 && (
                      <div className="font-mono text-[10px] text-slate-500 truncate">
                        › {dep.logs[dep.logs.length - 1].message}
                      </div>
                    )}
                  </div>
                );
              })}
        </div>
      </div>
    </div>
  );
};
