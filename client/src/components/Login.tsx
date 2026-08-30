import React, { useState } from 'react';
import { Shield, Eye, EyeOff, AlertTriangle } from 'lucide-react';

interface LoginProps {
  onLogin: (token: string, username: string, role: string, displayName: string) => void;
}

export default function Login({ onLogin }: LoginProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [animateError, setAnimateError] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setError('');
    setLoading(true);
    setAnimateError(false);

    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Access Denied: Invalid Badge ID or Passcode');
      }
      onLogin(data.token, data.username, data.role, data.display_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid credentials');
      setAnimateError(true);
    } finally {
      setLoading(false);
    }
  };

  const hasError = Boolean(error);

  return (
    <div className="auth-screen">
      <div className="auth-grain" />

      <div className="auth-shell">
        <form
          onSubmit={handleSubmit}
          className={`auth-card ${animateError ? 'animate-shake' : ''}`}
          data-has-error={hasError}
        >
          <span className="auth-card__corner" aria-hidden />

          {/* Top classification bar */}
          <div className="auth-classification">
            <span className="auth-classification__tag">
              <span className="auth-ping">
                <span className="auth-ping__wave" />
                <span className="auth-ping__dot" />
              </span>
              Restricted Access
            </span>
            <span className="auth-classification__ref">PRT-KSP-CIS</span>
          </div>

          {/* Brand / case-file stamp */}
          <div className="auth-brand">
            <div className="auth-brand__stamp">
              <Shield color="var(--accent-primary)" size={26} />
            </div>
            <h1 className="stamp-font auth-brand__title">
              KSP <span>CIS</span>
            </h1>
            <p className="auth-brand__sub">State Crime Intelligence Portal</p>
          </div>

          {/* Badge ID */}
          <div className="auth-field">
            <label htmlFor="login-username" className="auth-field__label">
              Badge ID
            </label>
            <input
              id="login-username"
              className="auth-input"
              type="text"
              placeholder="e.g. dysp1"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
              required
              aria-required="true"
              aria-invalid={hasError}
            />
          </div>

          {/* Passcode */}
          <div className="auth-field auth-field--tight">
            <label htmlFor="login-password" className="auth-field__label">
              Security Passcode
            </label>
            <div className="auth-input-wrap">
              <input
                id="login-password"
                className="auth-input auth-input--reveal"
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                aria-required="true"
                aria-invalid={hasError}
              />
              <button
                type="button"
                onClick={() => setShowPassword(p => !p)}
                className="auth-reveal"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {/* Alert */}
          {error && (
            <div className="auth-alert animate-fade-in" role="alert">
              <AlertTriangle size={15} />
              <span>{error}</span>
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            className="auth-submit"
            disabled={loading || !username.trim() || !password}
          >
            {loading ? 'Establishing Link...' : 'Establish Session'}
          </button>

          {/* Footer */}
          <div className="auth-footer">
            <p className="auth-footer__note">Authorized Personnel Only</p>
            <div className="auth-footer__creds">
              <span>ID: dysp1 / pass: demo1234</span>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
