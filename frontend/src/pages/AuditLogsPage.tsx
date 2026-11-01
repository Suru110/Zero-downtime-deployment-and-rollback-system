import React, { useState, useEffect } from 'react';
import api from '../api/client';
import { AuditLog } from '../types';
import { ScrollText, Shield, User, Clock, Filter, Terminal } from 'lucide-react';

export const AuditLogsPage: React.FC = () => {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedEntityFilter, setSelectedEntityFilter] = useState<string>('');

  const loadAuditLogs = async () => {
    try {
      const url = selectedEntityFilter
        ? `/audit-logs?entity_type=${selectedEntityFilter}&limit=100`
        : '/audit-logs?limit=100';
      const res = await api.get(url);
      setLogs(res.data.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAuditLogs();
  }, [selectedEntityFilter]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">Audit Trail & Compliance</h1>
          <p className="text-sm text-slate-400">
            Immutable operational activity log tracking every deployment trigger, rollback event, and configuration update.
          </p>
        </div>

        {/* Filter select */}
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-400" />
          <select
            value={selectedEntityFilter}
            onChange={(e) => setSelectedEntityFilter(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500"
          >
            <option value="">All Entities</option>
            <option value="deployment">Deployments</option>
            <option value="rollback">Rollbacks</option>
            <option value="project">Projects</option>
            <option value="release">Releases</option>
          </select>
        </div>
      </div>

      {/* Logs Table */}
      <div className="rounded-2xl glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/80 border-b border-slate-800 text-slate-400 uppercase font-semibold">
              <tr>
                <th className="px-6 py-3.5">Timestamp</th>
                <th className="px-6 py-3.5">Actor</th>
                <th className="px-6 py-3.5">Action</th>
                <th className="px-6 py-3.5">Target Entity</th>
                <th className="px-6 py-3.5">Event Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-400">
                    No audit records found matching filter.
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="px-6 py-3.5 whitespace-nowrap font-mono text-slate-400">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-3.5 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <User className="w-3.5 h-3.5 text-slate-400" />
                        <span className="font-semibold text-slate-200">{log.username || 'System Engine'}</span>
                      </div>
                    </td>
                    <td className="px-6 py-3.5 whitespace-nowrap">
                      <span className={`px-2 py-0.5 rounded-full font-semibold border ${
                        log.action.includes('rollback')
                          ? 'bg-purple-500/10 text-purple-400 border-purple-500/30'
                          : log.action.includes('fail')
                          ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                          : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                      }`}>
                        {log.action}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 whitespace-nowrap font-mono text-slate-300">
                      {log.entity_type}:{log.entity_id.substring(0, 8)}...
                    </td>
                    <td className="px-6 py-3.5 text-slate-400 font-mono text-[11px] max-w-xs truncate">
                      {JSON.stringify(log.details)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
