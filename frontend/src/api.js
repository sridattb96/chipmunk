const API = '/api';
const AUTH = '/auth';

function getToken() {
  return localStorage.getItem('chipmunk_token');
}

function parseApiError(err, fallback) {
  if (!err || typeof err !== 'object') return fallback;
  const d = err.detail ?? err.error ?? err.message;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length > 0 && d[0]?.msg) return d[0].msg;
  return fallback;
}

function authHeaders() {
  const token = getToken();
  return {
    ...(token && { Authorization: `Bearer ${token}` }),
    'Content-Type': 'application/json',
  };
}

export async function getConfig() {
  const res = await fetch(`${API}/config`);
  if (!res.ok) throw new Error('Failed to load config');
  return res.json();
}

export async function getMe() {
  const res = await fetch(`${AUTH}/me`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Not authenticated');
  return res.json();
}

export async function getDriveToken() {
  const res = await fetch(`${API}/drive/token`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to get Drive token');
  const data = await res.json();
  return data.access_token;
}

export async function uploadRecording(blob, name = 'Recording', duration = '0:00') {
  const formData = new FormData();
  formData.append('file', blob, 'recording.webm');
  formData.append('name', name);
  formData.append('duration', duration);
  const res = await fetch(`${API}/recordings/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(parseApiError(err, 'Upload failed'));
  }
  return res.json();
}

export async function listRecordings() {
  const res = await fetch(`${API}/recordings/all`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load recordings');
  return res.json();
}

export async function getRecording(id) {
  const res = await fetch(`${API}/recordings/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load recording');
  return res.json();
}

export async function searchRecordings(query) {
  const params = new URLSearchParams({ q: query });
  const res = await fetch(`${API}/recordings/search?${params}`, { headers: authHeaders() });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Search failed');
  }
  return res.json();
}

export function getStreamTranscribeUrl() {
  const token = getToken();
  if (!token) return null;
  // Connect directly to backend for WebSocket (avoids Vite proxy issues)
  const isDev = import.meta.env?.DEV;
  const wsBase = isDev ? 'ws://localhost:8000' : (window.location.origin.replace(/^http/, 'ws'));
  return `${wsBase}/api/recordings/stream-transcribe?token=${encodeURIComponent(token)}`;
}

export async function saveTranscript(name, duration, transcript) {
  const res = await fetch(`${API}/recordings/save-transcript`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ name, duration, transcript: transcript ?? '' }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(parseApiError(err, 'Save failed'));
  }
  return res.json();
}

export async function getTopicChains() {
  const res = await fetch(`${API}/topic-chains`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load topic chains');
  return res.json();
}

export async function getDbSnapshot() {
  const res = await fetch(`${API}/db/snapshot`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to load DB snapshot');
  return res.json();
}

export async function saveToDrive(folderId, recordingId, filename = 'call_notes.md') {
  const res = await fetch(`${API}/drive/save`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      folder_id: folderId,
      recording_id: recordingId,
      filename,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Save to Drive failed');
  }
  return res.json();
}
