import React, { useState } from 'react';
import { Shield } from 'lucide-react';

interface LoginProps {
  onLogin: (token: string, username: string, role: string, displayName: string) => void;
}

export default function Login({ onLogin }: LoginProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setError('');
    setLoading(true);
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Login failed');
      }
      onLogin(data.token, data.username, data.role, data.display_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="ambient-bg" />
      <form className="login-box" onSubmit={handleSubmit}>
        <div className="brand" style={{ justifyContent: 'center', marginBottom: '32px' }}>
          <div className="brand-icon">
            <Shield color="white" size={20} />
          </div>
          <h1>PS-1 <span>CIS</span></h1>
        </div>

        <label className="login-label" htmlFor="login-username">Badge ID</label>
        <input
          id="login-username"
          type="text"
          className="login-input"
          placeholder="e.g. si1"
          value={username}
          onChange={e => setUsername(e.target.value)}
          autoFocus
        />

        <label className="login-label" htmlFor="login-password">Password</label>
        <input
          id="login-password"
          type="password"
          className="login-input"
          placeholder="Password"
          value={password}
          onChange={e => setPassword(e.target.value)}
        />

        {error && <div className="login-error">{error}</div>}

        <button type="submit" className="login-submit" disabled={loading || !username.trim() || !password}>
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>
    </div>
  );
}
