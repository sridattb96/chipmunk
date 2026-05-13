import { Outlet, useLocation, Link } from 'react-router-dom';
import { useAuth } from './useAuth';
import './App.css';

export function AppShell() {
  const { logout } = useAuth();
  const location = useLocation();
  const isFullWidth = location.pathname.startsWith('/recordings') || location.pathname === '/db' || location.pathname === '/topic-chains';

  return (
    <div className={`app ${isFullWidth ? 'app-all-recordings' : ''}`}>
      <header className={`header ${isFullWidth ? 'header-all-recordings' : ''}`}>
        <Link to="/" className="header-brand-link">
          <span className="header-brand-symbol">∿</span>
          <h1 className="header-brand">Threadform</h1>
        </Link>
        <div className="user-row">
          <Link to="/recordings" className="header-link">Recordings</Link>
          <Link to="/topic-chains" className="header-link">Threads</Link>
          <button className="btn btn-text" onClick={logout}>Sign out</button>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
