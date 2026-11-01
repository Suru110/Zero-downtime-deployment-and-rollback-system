import React from 'react';
import { Release } from '../types';
import { X, ShieldAlert, ShieldCheck, AlertCircle } from 'lucide-react';
import { StatusBadge } from './StatusBadge';

interface ScanReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  release: Release | null;
}

export const ScanReportModal: React.FC<ScanReportModalProps> = ({ isOpen, onClose, release }) => {
  if (!isOpen || !release) return null;

  const results = release.scan_results || {};
  const vulns = results.vulnerabilities || [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl max-h-[85vh] flex flex-col">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-5 h-5 text-cyan-400" />
            <div>
              <h3 className="font-bold text-lg text-white">Trivy Vulnerability Scan Report</h3>
              <p className="text-xs text-slate-400">Release: {release.version} (Tag: {release.image_tag})</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto space-y-6">
          {/* Summary counters */}
          <div className="grid grid-cols-4 gap-3 text-center">
            <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl">
              <div className="text-2xl font-extrabold text-rose-400">{results.critical_count ?? 0}</div>
              <div className="text-[11px] font-semibold text-rose-300 uppercase">Critical</div>
            </div>
            <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl">
              <div className="text-2xl font-extrabold text-amber-400">{results.high_count ?? 0}</div>
              <div className="text-[11px] font-semibold text-amber-300 uppercase">High</div>
            </div>
            <div className="p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-xl">
              <div className="text-2xl font-extrabold text-yellow-400">{results.medium_count ?? 0}</div>
              <div className="text-[11px] font-semibold text-yellow-300 uppercase">Medium</div>
            </div>
            <div className="p-3 bg-slate-800 border border-slate-700 rounded-xl">
              <div className="text-2xl font-extrabold text-slate-300">{results.low_count ?? 0}</div>
              <div className="text-[11px] font-semibold text-slate-400 uppercase">Low</div>
            </div>
          </div>

          {/* Scanner Metadata */}
          <div className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl text-xs space-y-1">
            <div className="flex justify-between">
              <span className="text-slate-400">Scanner Engine:</span>
              <span className="font-mono text-slate-200">{results.scanner || 'Trivy v0.58.0'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Simulation Mode:</span>
              <span className={results.is_simulated ? 'text-amber-400 font-semibold' : 'text-emerald-400'}>
                {results.is_simulated ? 'Active (Realistic Mock)' : 'Live Cluster Scan'}
              </span>
            </div>
          </div>

          {/* CVE List */}
          <div>
            <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-3">Detected CVEs & Packages</h4>
            {vulns.length === 0 ? (
              <div className="p-6 bg-slate-950 border border-slate-800 rounded-xl text-center space-y-2">
                <ShieldCheck className="w-8 h-8 text-emerald-400 mx-auto" />
                <div className="text-sm font-semibold text-slate-200">Zero Critical Vulnerabilities</div>
                <p className="text-xs text-slate-400">This container image is clean and meets the release policy.</p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {vulns.map((v: any, idx: number) => (
                  <div key={idx} className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl space-y-1.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-rose-400">{v.cve_id}</span>
                        <span className="px-2 py-0.5 text-[10px] rounded bg-rose-500/20 text-rose-300 font-semibold">
                          {v.severity}
                        </span>
                      </div>
                      <span className="text-xs text-slate-400 font-mono">
                        {v.package} @ {v.installed_version}
                      </span>
                    </div>
                    {v.description && (
                      <p className="text-xs text-slate-400">{v.description}</p>
                    )}
                    {v.fixed_version && (
                      <div className="text-[11px] text-emerald-400 font-medium">
                        Fixed in: <span className="font-mono">{v.fixed_version}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/50 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-sm font-semibold bg-slate-800 hover:bg-slate-700 text-white transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
