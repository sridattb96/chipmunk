import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { listRecordings, getRecording, searchRecordings } from './api';
import { RecordingModal } from './RecordingModal';
import { downloadTranscript, exportToDrive } from './services/ExportService';
import './AllRecordings.css';

function formatDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now - d;
    const diffMins = diffMs / 60000;

    if (diffMins < 1) return 'less than a min ago';
    if (diffMins < 60) return `${Math.floor(diffMins)} minute${Math.floor(diffMins) === 1 ? '' : 's'} ago`;

    const isCurrentYear = d.getFullYear() === now.getFullYear();
    const monthDay = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    if (isCurrentYear) return monthDay;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return iso;
  }
}

const PILL_COLORS = [
  { bg: 'rgba(245,158,11,0.12)', text: '#fbbf24', border: 'rgba(245,158,11,0.35)' },  // amber
  { bg: 'rgba(59,130,246,0.12)', text: '#60a5fa', border: 'rgba(59,130,246,0.35)' },  // blue
  { bg: 'rgba(34,197,94,0.12)', text: '#4ade80', border: 'rgba(34,197,94,0.35)' },   // green
  { bg: 'rgba(236,72,153,0.12)', text: '#f472b6', border: 'rgba(236,72,153,0.35)' }, // pink
  { bg: 'rgba(139,92,246,0.12)', text: '#a78bfa', border: 'rgba(139,92,246,0.35)' }, // purple
  { bg: 'rgba(249,115,22,0.12)', text: '#fb923c', border: 'rgba(249,115,22,0.35)' }, // orange
  { bg: 'rgba(14,165,233,0.12)', text: '#38bdf8', border: 'rgba(14,165,233,0.35)' }, // sky
  { bg: 'rgba(244,63,94,0.12)',  text: '#fb7185', border: 'rgba(244,63,94,0.35)' },  // rose
  { bg: 'rgba(16,185,129,0.12)', text: '#34d399', border: 'rgba(16,185,129,0.35)' }, // emerald
  { bg: 'rgba(251,146,60,0.12)', text: '#fdba74', border: 'rgba(251,146,60,0.35)' }, // burnt orange
  { bg: 'rgba(56,189,248,0.12)', text: '#7dd3fc', border: 'rgba(56,189,248,0.35)' }, // light blue
  { bg: 'rgba(161,161,170,0.12)',text: '#a1a1aa', border: 'rgba(161,161,170,0.35)'},  // stone
  { bg: 'rgba(167,139,250,0.12)',text: '#c4b5fd', border: 'rgba(167,139,250,0.35)' }, // violet
  { bg: 'rgba(34,211,238,0.12)', text: '#67e8f9', border: 'rgba(34,211,238,0.35)' }, // cyan
  { bg: 'rgba(250,204,21,0.12)', text: '#fde047', border: 'rgba(250,204,21,0.35)' }, // yellow
];

function indexToColor(colorIndex) {
  return PILL_COLORS[colorIndex % PILL_COLORS.length];
}

function formatDetailDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const now = new Date();
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    if (d.toDateString() === now.toDateString()) return `Today at ${time}`;
    if (d.toDateString() === yesterday.toDateString()) return `Yesterday at ${time}`;
    const monthDay = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    if (d.getFullYear() === now.getFullYear()) return `${monthDay} at ${time}`;
    return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} at ${time}`;
  } catch {
    return iso;
  }
}

const WAVEFORM_BARS = [4, 8, 12, 7, 14, 9, 5, 11, 6, 10];

function WaveformIcon() {
  return (
    <svg width="29" height="14" viewBox="0 0 29 14" className="item-waveform" aria-hidden>
      {WAVEFORM_BARS.map((h, i) => (
        <rect key={i} x={i * 3} y={(14 - h) / 2} width="2" height={h} rx="1" fill="#c55a3c" />
      ))}
    </svg>
  );
}

function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debouncedValue;
}

export function AllRecordings() {
  const { id: selected } = useParams();
  const navigate = useNavigate();
  const selectedRef = useRef(selected);
  selectedRef.current = selected;

  const [list, setList] = useState([]);
  const [detail, setDetail] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showRecordingModal, setShowRecordingModal] = useState(false);
  const [exportingToDrive, setExportingToDrive] = useState(false);

  const debouncedQuery = useDebounce(searchQuery, 300);

  const loadList = useCallback(async (query) => {
    try {
      setError(null);
      const data = query
        ? await searchRecordings(query)
        : await listRecordings();
      setList(data);
      if (data.length > 0) {
        const ids = new Set(data.map((r) => r.id));
        if (!selectedRef.current || !ids.has(selectedRef.current)) {
          navigate('/recordings/' + data[0].id, { replace: true });
        }
      }
    } catch (e) {
      setError(e.message || 'Failed to load recordings');
      setList([]);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    setLoading(true);
    loadList(debouncedQuery);
  }, [debouncedQuery]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    getRecording(selected)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => { cancelled = true; };
  }, [selected]);

  const handleExportToDrive = useCallback(async () => {
    if (!detail) return;
    setExportingToDrive(true);
    try {
      await exportToDrive(detail);
    } catch (err) {
      if (err.message !== 'Cancelled') {
        setError(err.message || 'Export to Drive failed');
      }
    } finally {
      setExportingToDrive(false);
    }
  }, [detail]);

  const handleRecordingSaved = useCallback(async () => {
    setShowRecordingModal(false);
    const data = debouncedQuery
      ? await searchRecordings(debouncedQuery)
      : await listRecordings();
    setList(data);
    setLoading(false);
    if (data.length > 0) {
      navigate('/recordings/' + data[0].id, { replace: true });
    }
  }, [debouncedQuery, navigate]);

  return (
    <div className="all-recordings-page">
      <div className="all-recordings">
        <div className="all-recordings-header">
          <h1 className="all-recordings-title">Recordings</h1>
          <button
            type="button"
            className="btn btn-primary all-recordings-new-btn"
            onClick={() => setShowRecordingModal(true)}
          >
            <i className="fa-sharp fa-solid fa-plus" aria-hidden />
            <span>New Recording</span>
          </button>
        </div>
        <div className="all-recordings-search-bar">
          <i className="fa-solid fa-magnifying-glass all-recordings-search-icon" aria-hidden />
          <input
            type="search"
            className="all-recordings-search"
            placeholder="Search by title, summary, or topics"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

      {error && <div className="all-recordings-error">{error}</div>}
      {loading && <div className="all-recordings-loading">Loading...</div>}

      <div className="all-recordings-layout">
        <aside className="all-recordings-sidebar">
          {list.map((rec) => (
            <button
              key={rec.id}
              type="button"
              className={`all-recordings-item ${selected === rec.id ? 'selected' : ''}`}
              onClick={() => navigate('/recordings/' + rec.id)}
            >
              <WaveformIcon />
              <span className="item-name">{rec.name}</span>
              <span className="item-meta">
                {rec.duration} · {formatDate(rec.created_at)}
              </span>
            </button>
          ))}
        </aside>
        <main className="all-recordings-detail">
          {detail ? (
            <>
              <div className="detail-header">
                <h1 className="detail-title">{detail.name}</h1>
                <p className="detail-header-meta">{formatDetailDate(detail.created_at)} · {detail.duration}</p>
              </div>
<div className="detail-content">
                <section>
                  <h2 className="detail-heading">Summary</h2>
                  <p className="detail-summary">{detail.summary}</p>
                </section>
                {detail.topics?.length > 0 && (
                  <section className="detail-topics-section">
                    <span className="detail-topics-label">Topics:</span>
                    <div className="detail-topics">
                      {detail.topics.map((t, i) => {
                        const colorIdx = detail.topic_colors?.[t] ?? i;
                        const c = indexToColor(colorIdx);
                        return (
                          <span key={i} className="topic-chip" style={{ background: c.bg, color: c.text, borderColor: c.border }}>
                            {t}
                          </span>
                        );
                      })}
                    </div>
                  </section>
                )}
              </div>
              <div className="detail-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => downloadTranscript(detail)}
                  title="Download transcript as text file"
                >
                  <i className="fa-sharp fa-solid fa-download" aria-hidden />
                  <span>Download transcript</span>
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleExportToDrive}
                  disabled={exportingToDrive}
                  title="Save summary and transcript to Google Drive"
                >
                  <i className="fa-sharp fa-solid fa-arrow-up-right-from-square" aria-hidden />
                  <span>{exportingToDrive ? 'Opening...' : 'Export to Google Drive'}</span>
                </button>
              </div>
            </>
          ) : (
            <div className="detail-empty">
              {list.length === 0
                ? 'No recordings yet.'
                : 'Select a recording to view details.'}
            </div>
          )}
        </main>
      </div>
    </div>

    {showRecordingModal && (
      <RecordingModal
        onClose={() => setShowRecordingModal(false)}
        onSaved={handleRecordingSaved}
      />
    )}

    </div>
  );
}
