import { useState, useEffect } from 'react';
import { getMe } from './api';

const TOKEN_KEY = 'chipmunk_token';

export function useAuth() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    getMe()
      .then(setUser)
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false));
  }, []);

  const setToken = (token) => {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      getMe().then(setUser);
    } else {
      localStorage.removeItem(TOKEN_KEY);
      setUser(null);
    }
  };

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
  };

  return { user, loading, setToken, logout, isAuthenticated: !!user };
}
