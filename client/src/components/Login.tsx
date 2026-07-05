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

  // Input states for focus outline
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

  return (
    <div 
      className="min-h-screen w-full flex items-center justify-center relative overflow-hidden"
      style={{
        background: '#040407',
        fontFamily: "'Inter', sans-serif",
      }}
    >
      {/* Background Grid & Ambient Glows */}
      <div 
        className="absolute inset-0 opacity-20 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(255, 255, 255, 0.015) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.015) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
          maskImage: 'radial-gradient(circle 450px at center, black, transparent)',
          WebkitMaskImage: 'radial-gradient(circle 450px at center, black, transparent)',
        }}
      />
      
      {/* Accent Radial Glow */}
      <div 
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full blur-[140px] pointer-events-none" 
        style={{
          background: 'radial-gradient(circle, rgba(59, 130, 246, 0.05) 0%, transparent 70%)'
        }}
      />

      <div className="relative z-10 w-full max-w-[420px] px-6">
        <form 
          onSubmit={handleSubmit} 
          className={`w-full flex flex-col transition-all duration-300 ${
            animateError ? 'animate-shake' : ''
          }`}
          style={{
            background: 'rgba(13, 13, 18, 0.7)',
            backdropFilter: 'blur(30px)',
            WebkitBackdropFilter: 'blur(30px)',
            border: '1px solid rgba(255, 255, 255, 0.04)',
            borderRadius: '24px',
            padding: '40px',
            boxShadow: '0 24px 64px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
          }}
        >
          {/* Top Security Status Bar */}
          <div className="flex items-center justify-between w-full border-b border-white/5 pb-4 mb-6">
            <div className="flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-500 opacity-60"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
              </span>
              <span className="text-[9.5px] font-bold text-blue-400 uppercase tracking-widest">
                Secure Channel Active
              </span>
            </div>
            <span className="text-[9px] font-mono text-zinc-600 uppercase tracking-wider">
              PRT-KSP-CIS
            </span>
          </div>

          {/* Brand Header */}
          <div className="flex flex-col items-center text-center" style={{ marginBottom: '32px' }}>
            <div 
              className="w-14 h-14 flex items-center justify-center relative"
              style={{
                background: 'radial-gradient(circle, rgba(59, 130, 246, 0.12) 0%, transparent 70%)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '16px',
                marginTop: '28px',
                marginBottom: '20px',
                boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
              }}
            >
              <Shield className="text-blue-400 drop-shadow-[0_0_8px_rgba(59,130,246,0.4)]" size={26} />
              <div 
                className="absolute -bottom-1 -right-1 w-3.5 h-3.5 bg-[#0a0a0f] border rounded-full flex items-center justify-center"
                style={{ borderColor: 'rgba(255, 255, 255, 0.08)' }}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
              </div>
            </div>
            <h1 
              style={{
                fontSize: '24px',
                fontWeight: 800,
                color: 'white',
                letterSpacing: '-0.02em',
                margin: 0
              }}
            >
              KSP <span style={{ color: '#3b82f6', background: 'linear-gradient(135deg, #3b82f6 0%, #60a5fa 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>CIS</span>
            </h1>
            <p 
              style={{
                fontSize: '10px',
                fontWeight: 600,
                color: '#4b5563',
                textTransform: 'uppercase',
                letterSpacing: '0.12em',
                marginTop: '8px',
                marginBottom: 0
              }}
            >
              State Crime Intelligence Portal
            </p>
          </div>

          {/* Badge ID Input Group */}
          <div className="flex flex-col" style={{ marginBottom: '20px' }}>
            <label 
              htmlFor="login-username"
              style={{
                fontSize: '10px',
                fontWeight: 600,
                color: '#9ca3af',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                marginBottom: '8px',
                textAlign: 'left',
                display: 'block'
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
                background: 'rgba(0, 0, 0, 0.3)',
                border: error 
                  ? '1px solid rgba(239, 68, 68, 0.3)' 
                  : userFocused 
                    ? '1px solid #3b82f6' 
                    : '1px solid rgba(255, 255, 255, 0.06)',
                borderRadius: '12px',
                padding: '13px 16px',
                color: 'white',
                fontSize: '14px',
                outline: 'none',
                transition: 'all 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
                boxShadow: userFocused ? '0 0 0 1px rgba(59, 130, 246, 0.2)' : 'none',
              }}
            />
          </div>

          {/* Security Passcode Input Group */}
          <div className="flex flex-col" style={{ marginBottom: '24px' }}>
            <label 
              htmlFor="login-password"
              style={{
                fontSize: '10px',
                fontWeight: 600,
                color: '#9ca3af',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                marginBottom: '8px',
                textAlign: 'left',
                display: 'block'
              }}
            >
              Security Passcode
            </label>
            <div className="relative w-full">
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                onFocus={() => setPassFocused(true)}
                onBlur={() => setPassFocused(false)}
                required
                aria-required="true"
                style={{
                  width: '100%',
                  background: 'rgba(0, 0, 0, 0.3)',
                  border: error 
                    ? '1px solid rgba(239, 68, 68, 0.3)' 
                    : passFocused 
                      ? '1px solid #3b82f6' 
                      : '1px solid rgba(255, 255, 255, 0.06)',
                  borderRadius: '12px',
                  padding: '13px 40px 13px 16px',
                  color: 'white',
                  fontSize: '14px',
                  outline: 'none',
                  transition: 'all 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
                  boxShadow: passFocused ? '0 0 0 1px rgba(59, 130, 246, 0.2)' : 'none',
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(p => !p)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-555 hover:text-zinc-300 transition-colors"
                style={{ background: 'transparent', border: 'none', padding: 0, cursor: 'pointer' }}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {/* Alert - Sleek glass-bordered low profile alert box */}
          {error && (
            <div 
              className="flex items-start gap-3 animate-fade-in" 
              role="alert"
              style={{
                background: 'rgba(239, 68, 68, 0.02)',
                border: '1px solid rgba(239, 68, 68, 0.15)',
                borderRadius: '12px',
                padding: '12px 16px',
                color: '#f87171',
                fontSize: '12px',
                lineHeight: '1.4',
                boxSizing: 'border-box'
              }}
            >
              <AlertTriangle size={15} className="text-red-400 shrink-0 mt-0.5" />
              <span style={{ fontWeight: 500, textAlign: 'left' }}>{error}</span>
            </div>
          )}

          {/* Submit Button */}
          <button 
            type="submit" 
            className="w-full text-white font-semibold text-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            style={{
              marginTop: error ? '20px' : '24px',
              background: 'linear-gradient(180deg, #3b82f6 0%, #1d4ed8 100%)',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '12px',
              padding: '14px 16px',
              cursor: loading || !username.trim() || !password ? 'not-allowed' : 'pointer',
              boxShadow: '0 8px 24px rgba(37, 99, 235, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.15)',
              transition: 'all 0.2s ease',
            }}
            disabled={loading || !username.trim() || !password}
          >
            {loading ? 'Establishing Link...' : 'Establish Session'}
          </button>

          {/* Authorized Footer & Test accounts info */}
          <div 
            style={{
              marginTop: '32px',
              paddingTop: '20px',
              borderTop: '1px solid rgba(255, 255, 255, 0.04)',
              textAlign: 'center'
            }}
          >
            <p style={{ fontSize: '9.5px', color: '#4b5563', margin: 0, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>
              Authorized Personnel Only
            </p>
            <div 
              style={{
                marginTop: '8px',
                display: 'inline-flex',
                gap: '12px',
                fontSize: '9.5px',
                fontFamily: 'monospace',
                color: '#6b7280',
                background: 'rgba(0, 0, 0, 0.2)',
                padding: '4px 10px',
                borderRadius: '6px',
                border: '1px solid rgba(255, 255, 255, 0.03)'
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
