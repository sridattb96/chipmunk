import { useEffect } from 'react';
import { Outlet, useLocation, Link } from 'react-router-dom';
import { useAuth } from './useAuth';
import './App.css';

const AUTH_URL = `${import.meta.env.VITE_API_URL || ''}/auth/google`;

export function AppShell() {
  const { user, loading, setToken, logout, isAuthenticated } = useAuth();
  const location = useLocation();
  const isAllRecordings = location.pathname === '/' || location.pathname.startsWith('/recordings') || location.pathname === '/all' || location.pathname === '/db' || location.pathname === '/topic-chains';

  // Capture token from OAuth redirect (?token=...)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (token) {
      setToken(token);
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [setToken]);

  if (loading) {
    return (
      <div className="app">
        <div className="loading">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="app">
        <header className="header">
          <h1>Threadform</h1>
          <p>Record calls, get transcripts and summaries, save to Drive.</p>
        </header>
        <div className="auth-section">
          <a href={AUTH_URL} className="btn btn-primary btn-google">
            Sign in with Google
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className={`app ${isAllRecordings ? 'app-all-recordings' : ''}`}>
      <header className={`header ${isAllRecordings ? 'header-all-recordings' : ''}`}>
        <h1 className="header-brand">Threadform</h1>
        <div className="user-row">
          <Link to="/" className="header-link">All Recordings</Link>
          <Link to="/topic-chains" className="header-link">Topic Chains</Link>
          <Link to="/db" className="header-link">DB</Link>
          <button className="btn btn-text" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
