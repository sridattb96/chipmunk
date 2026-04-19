import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './useAuth';
import { AppShell } from './AppShell';
import { AllRecordings } from './AllRecordings';
import { DbSnapshot } from './DbSnapshot';
import { TopicChains } from './TopicChains';
import './App.css';

const AUTH_URL = `${import.meta.env.VITE_API_URL || ''}/auth/google`;

function UnauthenticatedApp() {
  return (
    <div className="app">
      <header className="header">
        <h1>Chipmunk</h1>
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

function AuthenticatedRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<AllRecordings />} />
        <Route path="recordings/:id" element={<AllRecordings />} />
        <Route path="db" element={<DbSnapshot />} />
        <Route path="topic-chains" element={<TopicChains />} />
      </Route>
      <Route path="/all" element={<Navigate to="/" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  const { loading, setToken, isAuthenticated } = useAuth();

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
    return <UnauthenticatedApp />;
  }

  return (
    <BrowserRouter>
      <AuthenticatedRoutes />
    </BrowserRouter>
  );
}

export default App;
