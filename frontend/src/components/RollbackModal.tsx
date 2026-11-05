import React, { useState } from 'react';
import { Deployment } from '../types';
import api from '../api/client';
import { X, RotateCcw, AlertTriangle } from 'lucide-react';

interface RollbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  deployment: Deployment | null;
  onRollbackCompleted: () => void;
}

export const RollbackModal: React.FC<RollbackModalProps> = ({
  isOpen,
  onClose,
  deployment,
  onRollbackCompleted
}) => {
  const [reason, setReason] = useState('Critical regression detected in production metrics');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen || !deployment) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await api.post('/rollbacks', {
        deployment_id: deployment.id,
        reason: reason
      });
      onRollbackCompleted();
      onClose();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to execute rollback');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2 text-purple-400">
            <RotateCcw className="w-5 h-5" />
            <h3 className="font-bold text-lg text-white">Emergency Rollback</h3>
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

          <div className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-300 space-y-1">
            <div>Deployment ID: <span className="font-mono text-purple-300">{deployment.id.substring(0, 12)}...</span></div>
            <div>Strategy: <span className="text-white capitalize">{deployment.strategy}</span></div>
            <div>Adapter: <span className="text-slate-400">{deployment.adapter_name}</span></div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Rollback Justification / Reason *
            </label>
            <textarea
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-purple-500 placeholder:text-slate-600"
              placeholder="Explain the incident or failure driving this rollback..."
            />
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
              disabled={loading}
              className="px-5 py-2.5 rounded-xl text-sm font-bold bg-purple-600 hover:bg-purple-500 text-white shadow-lg shadow-purple-600/20 disabled:opacity-50 transition-all flex items-center gap-2"
            >
              <RotateCcw className="w-4 h-4" />
              <span>{loading ? 'Rolling back...' : 'Confirm Rollback'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
