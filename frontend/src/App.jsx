import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from './useAuth';
import { AppShell } from './AppShell';
import { AllRecordings } from './AllRecordings';
import { DbSnapshot } from './DbSnapshot';
import { TopicChains } from './TopicChains';
import { LandingPage } from './LandingPage';
import './App.css';

function AppRoutes() {
  const { loading, setToken, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (token) {
      setToken(token);
      window.history.replaceState({}, '', '/recordings');
      navigate('/recordings', { replace: true });
    }
  }, [setToken, navigate]);

  if (loading) {
    return <div className="app"><div className="loading">Loading...</div></div>;
  }

  const authGuard = isAuthenticated ? <AppShell /> : <Navigate to="/" replace />;

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route element={authGuard}>
        <Route path="/recordings" element={<AllRecordings />} />
        <Route path="/recordings/:id" element={<AllRecordings />} />
        <Route path="/db" element={<DbSnapshot />} />
        <Route path="/topic-chains" element={<TopicChains />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}

export default App;
