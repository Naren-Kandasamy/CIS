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

  const [userFocused, setUserFocused] = useState(false);
  const [passFocused, setPassFocused] = useState(false);

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

  const inkBorder = (focused: boolean) =>
    error ? '1px solid #8a2a24' : focused ? '1px solid #8a2a24' : '1px solid rgba(43, 33, 20, 0.22)';

  return (
    <div
      className="min-h-screen w-full flex items-center justify-center relative overflow-hidden"
      style={{
        background: '#e9e1cd',
        fontFamily: "'Source Serif 4', Georgia, serif",
      }}
    >
      {/* Paper grain + ruled desk texture, no glows */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            radial-gradient(circle at 20% 25%, rgba(43,33,20,0.05), transparent 45%),
            radial-gradient(circle at 80% 70%, rgba(43,33,20,0.05), transparent 45%),
            repeating-linear-gradient(0deg, rgba(43,33,20,0.025) 0px, rgba(43,33,20,0.025) 1px, transparent 1px, transparent 3px)
          `,
        }}
      />

      <div className="relative z-10 w-full max-w-[440px] px-6">
        <form
          onSubmit={handleSubmit}
          className={`w-full flex flex-col transition-all duration-300 ${animateError ? 'animate-shake' : ''}`}
          style={{
            background: '#f4eeda',
            border: '1px solid rgba(43, 33, 20, 0.18)',
            borderRadius: '2px',
            padding: '40px',
            boxShadow: '2px 4px 0 rgba(43, 33, 20, 0.12)',
            position: 'relative',
          }}
        >
          {/* folded corner, matches dossier-panel */}
          <div
            style={{
              position: 'absolute', top: 0, right: 0, width: 0, height: 0,
              borderStyle: 'solid', borderWidth: '0 22px 22px 0',
              borderColor: 'transparent #ddd3b6 transparent transparent',
            }}
          />

          {/* Top classification bar */}
          <div className="flex items-center justify-between w-full pb-4 mb-6" style={{ borderBottom: '1px dashed rgba(43,33,20,0.25)' }}>
            <div className="flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60" style={{ background: '#8a2a24' }} />
                <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: '#8a2a24' }} />
              </span>
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '9.5px', fontWeight: 700, color: '#8a2a24', textTransform: 'uppercase', letterSpacing: '0.15em' }}>
                Restricted Access
              </span>
            </div>
            <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '9px', color: '#8a7d67', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
              PRT-KSP-CIS
            </span>
          </div>

          {/* Brand / case-file stamp */}
          <div className="flex flex-col items-center text-center" style={{ marginBottom: '28px' }}>
            <div
              className="w-14 h-14 flex items-center justify-center relative"
              style={{
                background: '#f4eeda',
                border: '2px solid #8a2a24',
                borderRadius: '4px',
                marginBottom: '18px',
                transform: 'rotate(-2deg)',
                boxShadow: '2px 2px 0 rgba(43,33,20,0.18)',
              }}
            >
              <Shield color="#8a2a24" size={26} />
            </div>
            <h1
              className="stamp-font"
              style={{ fontSize: '22px', fontWeight: 400, color: '#241d14', letterSpacing: '0.02em', margin: 0 }}
            >
              KSP <span style={{ color: '#8a2a24' }}>CIS</span>
            </h1>
            <p
              style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: '10px',
                fontWeight: 600,
                color: '#8a7d67',
                textTransform: 'uppercase',
                letterSpacing: '0.12em',
                marginTop: '8px',
                marginBottom: 0,
              }}
            >
              State Crime Intelligence Portal
            </p>
          </div>

          {/* Badge ID */}
          <div className="flex flex-col" style={{ marginBottom: '18px' }}>
            <label
              htmlFor="login-username"
              style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: '10px',
                fontWeight: 600,
                color: '#5c5140',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                marginBottom: '8px',
                display: 'block',
              }}
            >
              Badge ID
            </label>
            <input
              id="login-username"
              type="text"
              placeholder="e.g. dysp1"
              value={username}
              onChange={e => setUsername(e.target.value)}
              onFocus={() => setUserFocused(true)}
              onBlur={() => setUserFocused(false)}
              autoFocus
              required
              aria-required="true"
              style={{
                width: '100%',
                background: '#e9e1cd',
                border: inkBorder(userFocused),
                borderRadius: '2px',
                padding: '13px 16px',
                color: '#241d14',
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: '14px',
                outline: 'none',
                transition: 'border-color 0.2s',
              }}
            />
          </div>

          {/* Passcode */}
          <div className="flex flex-col" style={{ marginBottom: '22px' }}>
            <label
              htmlFor="login-password"
              style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: '10px',
                fontWeight: 600,
                color: '#5c5140',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                marginBottom: '8px',
                display: 'block',
              }}
            >
              Security Passcode
            </label>
            <div className="relative w-full">
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                onFocus={() => setPassFocused(true)}
                onBlur={() => setPassFocused(false)}
                required
                aria-required="true"
                style={{
                  width: '100%',
                  background: '#e9e1cd',
                  border: inkBorder(passFocused),
                  borderRadius: '2px',
                  padding: '13px 40px 13px 16px',
                  color: '#241d14',
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: '14px',
                  outline: 'none',
                  transition: 'border-color 0.2s',
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(p => !p)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 transition-colors"
                style={{ background: 'transparent', border: 'none', padding: 0, cursor: 'pointer', color: '#8a7d67' }}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {/* Alert */}
          {error && (
            <div
              className="flex items-start gap-3 animate-fade-in"
              role="alert"
              style={{
                background: '#f7e6e5',
                border: '1px solid rgba(138, 42, 36, 0.35)',
                borderRadius: '2px',
                padding: '12px 16px',
                color: '#6f211c',
                fontSize: '12px',
                lineHeight: '1.4',
                boxSizing: 'border-box',
              }}
            >
              <AlertTriangle size={15} className="shrink-0 mt-0.5" style={{ color: '#8a2a24' }} />
              <span style={{ fontWeight: 500, textAlign: 'left' }}>{error}</span>
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            className="w-full font-semibold text-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            style={{
              marginTop: error ? '20px' : '24px',
              background: '#8a2a24',
              color: '#f4eeda',
              border: '1px solid #6f211c',
              borderRadius: '2px',
              padding: '14px 16px',
              cursor: loading || !username.trim() || !password ? 'not-allowed' : 'pointer',
              boxShadow: '2px 2px 0 rgba(43,33,20,0.15)',
              fontFamily: "'IBM Plex Mono', monospace",
              letterSpacing: '0.04em',
            }}
            disabled={loading || !username.trim() || !password}
          >
            {loading ? 'Establishing Link...' : 'Establish Session'}
          </button>

          {/* Footer */}
          <div
            style={{
              marginTop: '32px',
              paddingTop: '18px',
              borderTop: '1px dashed rgba(43,33,20,0.2)',
              textAlign: 'center',
            }}
          >
            <p style={{ fontSize: '9.5px', color: '#8a7d67', margin: 0, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>
              Authorized Personnel Only
            </p>
            <div
              style={{
                marginTop: '8px',
                display: 'inline-flex',
                gap: '12px',
                fontSize: '9.5px',
                fontFamily: "'IBM Plex Mono', monospace",
                color: '#5c5140',
                background: '#e9e1cd',
                padding: '4px 10px',
                borderRadius: '2px',
                border: '1px solid rgba(43,33,20,0.12)',
              }}
            >
              <span>ID: dysp1 / pass: demo1234</span>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
