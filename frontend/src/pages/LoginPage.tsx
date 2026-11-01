import React, { useState } from 'react';
import { AlertCircle, Eye, EyeOff, Lock, Mail, Rocket } from 'lucide-react';
import api from '../api/client';
import { useAuth } from '../contexts/AuthContext';

const goTo = (path: string) => {
  window.location.assign(path);
};

const getErrorMessage = (error: any) =>
  error.response?.data?.detail ||
  error.response?.data?.error?.message ||
  'Unable to sign in. Please check your email and password.';

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await api.post('/auth/login', { email, password });
      const data = response.data.data;
      login(data.access_token, data.user, rememberMe);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell subtitle="Secure deployment orchestration for modern teams">
      <div className="p-8 rounded-2xl glass-card space-y-6 shadow-2xl">
        <div>
          <h2 className="text-xl font-bold text-white">Welcome back</h2>
          <p className="mt-1 text-sm text-slate-400">Sign in to continue to your dashboard.</p>
        </div>
        {error && <ErrorMessage message={error} />}
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Email address" icon={<Mail />} type="email" value={email} onChange={setEmail} placeholder="you@company.com" />
          <PasswordField label="Password" value={password} show={showPassword} onChange={setPassword} onToggle={() => setShowPassword(!showPassword)} />
          <label className="flex items-center gap-2 text-sm text-slate-400">
            <input type="checkbox" checked={rememberMe} onChange={(event) => setRememberMe(event.target.checked)} className="accent-emerald-500" />
            Remember me on this device
          </label>
          <SubmitButton loading={loading} label="Sign in" />
        </form>
        <p className="text-center text-sm text-slate-400">
          Don't have an account?{' '}
          <button type="button" onClick={() => goTo('/register')} className="font-semibold text-emerald-400 hover:text-emerald-300">Register</button>
        </p>
      </div>
    </AuthShell>
  );
};

export const AuthShell: React.FC<{ subtitle: string; children: React.ReactNode }> = ({ subtitle, children }) => (
  <div className="min-h-screen bg-slate-950 flex flex-col justify-center items-center p-4">
    <div className="w-full max-w-md space-y-8">
      <div className="text-center space-y-2">
        <div className="inline-flex w-14 h-14 rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-400 items-center justify-center shadow-xl shadow-emerald-500/20 mb-2">
          <Rocket className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-3xl font-extrabold text-white tracking-tight">Release<span className="text-emerald-400">Pilot</span></h1>
        <p className="text-sm text-slate-400">{subtitle}</p>
      </div>
      {children}
    </div>
  </div>
);

export const ErrorMessage: React.FC<{ message: string }> = ({ message }) => (
  <div className="p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-sm text-rose-400 flex items-center gap-2">
    <AlertCircle className="w-4 h-4 shrink-0" />
    <span>{message}</span>
  </div>
);

export const Field: React.FC<{ label: string; icon: React.ReactNode; type: string; value: string; onChange: (value: string) => void; placeholder: string }> = ({ label, icon, type, value, onChange, placeholder }) => (
  <div>
    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">{label}</label>
    <div className="relative">
      <span className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2">{icon}</span>
      <input type={type} required value={value} onChange={(event) => onChange(event.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500" placeholder={placeholder} />
    </div>
  </div>
);

export const PasswordField: React.FC<{ label: string; value: string; show: boolean; onChange: (value: string) => void; onToggle: () => void }> = ({ label, value, show, onChange, onToggle }) => (
  <div>
    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">{label}</label>
    <div className="relative">
      <Lock className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
      <input type={show ? 'text' : 'password'} required value={value} onChange={(event) => onChange(event.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-11 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500" placeholder="Enter your password" />
      <button type="button" onClick={onToggle} aria-label={show ? 'Hide password' : 'Show password'} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
        {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </div>
  </div>
);

export const SubmitButton: React.FC<{ loading: boolean; label: string }> = ({ loading, label }) => (
  <button type="submit" disabled={loading} className="w-full py-3 rounded-xl font-bold text-sm bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-white shadow-lg shadow-emerald-600/20 disabled:opacity-50 transition-all">
    {loading ? 'Please wait...' : label}
  </button>
);
