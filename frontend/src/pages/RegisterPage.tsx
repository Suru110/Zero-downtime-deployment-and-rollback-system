import React, { useState } from 'react';
import { Mail, User } from 'lucide-react';
import api from '../api/client';
import { AuthShell, ErrorMessage, Field, PasswordField, SubmitButton } from './LoginPage';

const goToLogin = () => {
  window.location.assign('/login');
};

export const RegisterPage: React.FC = () => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (password.length < 8 || !/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password)) {
      setError('Password must be at least 8 characters and include uppercase, lowercase, and a number.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    try {
      await api.post('/auth/register', { name, email, password });
      setSuccess(true);
      window.setTimeout(goToLogin, 900);
    } catch (requestError: any) {
      const detail = requestError.response?.data?.detail || requestError.response?.data?.error?.message;
      setError(detail || 'Unable to create your account. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell subtitle="Create your ReleasePilot workspace account">
      <div className="p-8 rounded-2xl glass-card space-y-6 shadow-2xl">
        <div>
          <h2 className="text-xl font-bold text-white">Create an account</h2>
          <p className="mt-1 text-sm text-slate-400">Start managing releases securely.</p>
        </div>
        {error && <ErrorMessage message={error} />}
        {success && <div className="p-3.5 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-sm text-emerald-400">Account created. Redirecting to sign in...</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Full name" icon={<User />} type="text" value={name} onChange={setName} placeholder="Your full name" />
          <Field label="Email address" icon={<Mail />} type="email" value={email} onChange={setEmail} placeholder="you@company.com" />
          <PasswordField label="Password" value={password} show={showPassword} onChange={setPassword} onToggle={() => setShowPassword(!showPassword)} />
          <PasswordField label="Confirm password" value={confirmPassword} show={showConfirmPassword} onChange={setConfirmPassword} onToggle={() => setShowConfirmPassword(!showConfirmPassword)} />
          <p className="text-xs text-slate-500">Use at least 8 characters with uppercase, lowercase, and a number.</p>
          <SubmitButton loading={loading} label="Create account" />
        </form>
        <p className="text-center text-sm text-slate-400">
          Already have an account?{' '}
          <button type="button" onClick={goToLogin} className="font-semibold text-emerald-400 hover:text-emerald-300">Login</button>
        </p>
      </div>
    </AuthShell>
  );
};
