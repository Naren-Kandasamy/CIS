import { Navigate, useNavigate } from 'react-router-dom';
import Login from '../components/Login';
import { useAuthStore } from '../stores/authStore';

export default function LoginPage() {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);
  const login = useAuthStore((s) => s.login);

  if (token) return <Navigate to="/cases" replace />;

  return (
    <Login
      onLogin={(tok, _username, role, displayName) => {
        login(tok, displayName, role);
        navigate('/cases', { replace: true });
      }}
    />
  );
}
