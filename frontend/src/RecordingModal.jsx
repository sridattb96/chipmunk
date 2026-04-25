import { useState, useRef, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { uploadRecording, getConfig, getStreamTranscribeUrl, saveTranscript } from './api';
import './RecordingModal.css';

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function RecordingModal({ onClose, onSaved }) {
  const [step, setStep] = useState(1); // 1 = record, 2 = name
  const [isRecording, setIsRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const [recordingName, setRecordingName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [transcriptionMode, setTranscriptionMode] = useState('batch');
  const [liveTranscript, setLiveTranscript] = useState('');
  const [isFinalizing, setIsFinalizing] = useState(false); // stream mode: waiting for "done"
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const durationRef = useRef(0);
  const pendingRecordingRef = useRef(null);
  const canvasRef = useRef(null);
  const analyserRef = useRef(null);
  const audioContextRef = useRef(null);
  const animationFrameRef = useRef(null);
  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const transcriptPartsRef = useRef([]);
  const reconnectTimerRef = useRef(null);

  useEffect(() => {
    getConfig().then((c) => setTranscriptionMode(c.transcriptionMode || 'batch')).catch(() => {});
  }, []);

  const startRecordingBatch = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      // Web Audio API for waveform visualization
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      audioContextRef.current = audioContext;
      analyserRef.current = analyser;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
        if (audioContextRef.current) {
          audioContextRef.current.close();
        }
        stream.getTracks().forEach((t) => t.stop());
        if (chunksRef.current.length > 0) {
          const blob = new Blob(chunksRef.current, { type: mimeType });
          pendingRecordingRef.current = { blob, duration: durationRef.current };
          setStep(2);
        }
        chunksRef.current = [];
      };

      recorder.start(1000);
      mediaRecorderRef.current = recorder;
      durationRef.current = 0;
      setIsRecording(true);
      setDuration(0);
      timerRef.current = setInterval(() => {
        durationRef.current += 1;
        setDuration((d) => d + 1);
      }, 1000);
    } catch (err) {
      console.error(err);
      alert('Could not access microphone. Please allow microphone access.');
    }
  }, []);

  const startRecordingStream = useCallback(async () => {
    const wsUrl = getStreamTranscribeUrl();
    if (!wsUrl) {
      alert('Not authenticated. Please sign in again.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      const recorder = new MediaRecorder(stream);

      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      audioContextRef.current = audioContext;
      analyserRef.current = analyser;

      transcriptPartsRef.current = [];

      const makeOnMessage = () => (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.transcript) {
            if (msg.is_final) {
              transcriptPartsRef.current.push(msg.transcript);
              setLiveTranscript(transcriptPartsRef.current.join(' '));
            } else {
              const base = transcriptPartsRef.current.join(' ');
              setLiveTranscript(base ? `${base} ${msg.transcript}` : msg.transcript);
            }
          }
          if (msg.type === 'done') {
            pendingRecordingRef.current = {
              transcript: msg.transcript || transcriptPartsRef.current.join(' '),
              duration: durationRef.current,
            };
            setIsFinalizing(false);
            setStep(2);
            if (wsRef.current) {
              wsRef.current.close();
              wsRef.current = null;
            }
          }
          if (msg.type === 'error') {
            setUploadError(msg.error || 'Transcription failed');
            setIsFinalizing(false);
            if (wsRef.current) {
              wsRef.current.close();
              wsRef.current = null;
            }
          }
        } catch (_) {}
      };

      // Reconnects the Deepgram WebSocket every ~8.5 min to avoid the 10-min session limit.
      // Audio keeps flowing from the same MediaRecorder — only the socket is swapped.
      const performReconnect = () => {
        const newWsUrl = getStreamTranscribeUrl();
        if (!newWsUrl || !mediaRecorderRef.current) return;

        const oldWs = wsRef.current;
        const newWs = new WebSocket(newWsUrl);

        newWs.onmessage = makeOnMessage();
        newWs.onerror = () => { setUploadError('WebSocket reconnect failed'); setIsFinalizing(false); };
        newWs.onclose = () => {};

        newWs.onopen = () => {
          if (mediaRecorderRef.current?.state === 'recording') {
            mediaRecorderRef.current.ondataavailable = (ev) => {
              if (ev.data.size > 0 && newWs.readyState === WebSocket.OPEN) {
                ev.data.arrayBuffer().then((buf) => newWs.send(buf));
              }
            };
          }
          wsRef.current = newWs;

          if (oldWs?.readyState === WebSocket.OPEN) {
            // Null out handlers before CloseStream so its 'done' doesn't end the recording
            oldWs.onmessage = () => {};
            oldWs.onclose = () => {};
            oldWs.send(JSON.stringify({ type: 'CloseStream' }));
            setTimeout(() => { if (oldWs.readyState !== WebSocket.CLOSED) oldWs.close(); }, 2000);
          }
        };
      };

      const ws = new WebSocket(wsUrl);

      ws.onmessage = makeOnMessage();
      ws.onerror = () => {
        setUploadError('WebSocket error');
        setIsFinalizing(false);
      };
      ws.onclose = () => {
        stream.getTracks().forEach((t) => t.stop());
        if (audioContextRef.current) audioContextRef.current.close();
        setIsFinalizing(false);
      };

      ws.onopen = () => {
        recorder.ondataavailable = (ev) => {
          if (ev.data.size > 0 && ws.readyState === WebSocket.OPEN) {
            ev.data.arrayBuffer().then((buf) => ws.send(buf));
          }
        };
        recorder.start(250);
        mediaRecorderRef.current = recorder;
        wsRef.current = ws;
      };

      durationRef.current = 0;
      setLiveTranscript('');
      setIsRecording(true);
      setDuration(0);
      timerRef.current = setInterval(() => {
        durationRef.current += 1;
        setDuration((d) => d + 1);
        if (durationRef.current >= 1800) {
          // Auto-stop at 30 min
          clearInterval(timerRef.current);
          timerRef.current = null;
          if (reconnectTimerRef.current) {
            clearInterval(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
          }
          setIsFinalizing(true);
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'CloseStream' }));
          }
          if (mediaRecorderRef.current?.state !== 'inactive') {
            mediaRecorderRef.current?.stop();
            mediaRecorderRef.current = null;
          }
          if (streamRef.current) {
            streamRef.current.getTracks().forEach((t) => t.stop());
            streamRef.current = null;
          }
          setIsRecording(false);
        }
      }, 1000);

      // Reconnect every 8.5 min before Deepgram's 10-min session limit
      reconnectTimerRef.current = setInterval(performReconnect, 510_000);
    } catch (err) {
      console.error(err);
      alert('Could not access microphone. Please allow microphone access.');
    }
  }, []);

  const startRecording = useCallback(() => {
    if (transcriptionMode === 'stream') {
      startRecordingStream();
    } else {
      startRecordingBatch();
    }
  }, [transcriptionMode, startRecordingBatch, startRecordingStream]);

  const stopRecording = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearInterval(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (transcriptionMode === 'stream') {
      setIsFinalizing(true);
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'CloseStream' }));
      }
      if (mediaRecorderRef.current?.state !== 'inactive') {
        mediaRecorderRef.current?.stop();
        mediaRecorderRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
    } else {
      if (mediaRecorderRef.current?.state !== 'inactive') {
        mediaRecorderRef.current?.stop();
        mediaRecorderRef.current = null;
      }
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setIsRecording(false);
  }, [transcriptionMode]);

  const handleSave = async () => {
    const pending = pendingRecordingRef.current;
    if (!pending) return;
    const name = recordingName.trim() || 'Recording';
    const durationStr = formatDuration(pending.duration);
    setUploading(true);
    setUploadError(null);
    try {
      if (transcriptionMode === 'stream') {
        if (pending.blob) {
          setUploadError('Stream mode does not have audio—cannot upload. Please record again.');
          return;
        }
        await saveTranscript(name, durationStr, pending.transcript ?? '');
      } else {
        if (!pending.blob) {
          setUploadError('No recording available.');
          return;
        }
        await uploadRecording(pending.blob, name, durationStr);
      }
      pendingRecordingRef.current = null;
      onSaved?.();
      onClose?.();
    } catch (err) {
      setUploadError(err?.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleClose = () => {
    if (reconnectTimerRef.current) {
      clearInterval(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
    }
    onClose?.();
  };

  const formatTime = (sec) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const drawIdleWaveform = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const centerY = canvas.height / 2;
    ctx.save();
    ctx.strokeStyle = '#93c5fd';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 6]);
    ctx.beginPath();
    ctx.moveTo(0, centerY);
    ctx.lineTo(canvas.width, centerY);
    ctx.stroke();
    ctx.restore();
  }, []);

  const drawWaveform = useCallback(() => {
    const canvas = canvasRef.current;
    const analyser = analyserRef.current;
    if (!canvas || !analyser) return;

    const ctx = canvas.getContext('2d');
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    const barCount = 48;
    const barWidth = canvas.width / barCount - 2;

    const draw = () => {
      animationFrameRef.current = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(dataArray);

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const step = Math.floor(bufferLength / barCount);
      for (let i = 0; i < barCount; i++) {
        const value = dataArray[i * step] || 0;
        const barHeight = (value / 255) * (canvas.height * 0.8);
        const x = i * (barWidth + 2);
        const y = (canvas.height - barHeight) / 2;

        const gradient = ctx.createLinearGradient(0, canvas.height, 0, 0);
        gradient.addColorStop(0, '#2563eb');
        gradient.addColorStop(0.5, '#3b82f6');
        gradient.addColorStop(1, '#60a5fa');
        ctx.fillStyle = gradient;
        ctx.fillRect(x, y, barWidth, Math.max(2, barHeight));
      }
    };
    draw();
  }, []);

  useEffect(() => {
    if (isRecording && canvasRef.current && analyserRef.current) {
      drawWaveform();
    } else if (step === 1 && canvasRef.current) {
      drawIdleWaveform();
    }
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isRecording, step, drawWaveform, drawIdleWaveform]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || isRecording) return;
    const observer = new ResizeObserver(() => {
      if (step === 1) drawIdleWaveform();
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [step, isRecording, drawIdleWaveform]);

  const modalContent = (
    <div
      className="recording-modal-overlay"
      onClick={handleClose}
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.4)',
        zIndex: 99999,
      }}
    >
      <div
        className="recording-modal"
        onClick={(e) => e.stopPropagation()}
        style={{
          position: 'relative',
          backgroundColor: 'var(--surface)',
          borderRadius: 12,
          width: step === 1 && transcriptionMode === 'stream' ? 720 : 400,
          maxWidth: '95vw',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.2)',
        }}
      >
        <button
          type="button"
          className="recording-modal-close"
          onClick={handleClose}
          aria-label="Close"
        >
          ×
        </button>
        <div className="recording-modal-body">
          {step === 1 ? (
            <div className={`recording-modal-step recording-modal-step-record recording-modal-record-layout ${transcriptionMode === 'batch' ? 'recording-modal-record-single' : ''}`}>
              <h3>New Recording</h3>
              <div className="recording-modal-record-grid">
                <div className="recording-modal-record-left">
                  <div className="recording-modal-waveform-container">
                    <canvas
                      ref={canvasRef}
                      className="recording-modal-waveform"
                      width={320}
                      height={140}
                    />
                  </div>
                  {isRecording ? (
                    <>
                      <div className="recording-modal-indicator recording-modal-indicator-recording">
                        <span className="recording-modal-pulse" /> Recording {formatTime(duration)}
                      </div>
                      <button type="button" className="recording-modal-btn recording-modal-btn-stop" onClick={stopRecording}>
                        Stop Recording
                      </button>
                    </>
                  ) : isFinalizing ? (
                    <>
                      <div className="recording-modal-indicator" style={{ padding: '0.5rem 0' }}>
                        <span className="recording-modal-pulse" style={{ opacity: 0.7 }} /> Processing transcript...
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="recording-modal-indicator recording-modal-indicator-idle">
                        <span className="recording-modal-dot-idle" /> Not recording
                      </div>
                      <button type="button" className="recording-modal-btn recording-modal-btn-record" onClick={startRecording}>
                        Record
                      </button>
                    </>
                  )}
                </div>
                {transcriptionMode === 'stream' && (
                  <div className="recording-modal-record-right">
                    <div className="recording-modal-transcript-panel">
                      <div className="recording-modal-transcript-label">Live transcription</div>
                      <div className="recording-modal-transcript-content">
                        {isFinalizing ? (
                          <span className="recording-modal-transcript-placeholder">Processing...</span>
                        ) : liveTranscript ? (
                          liveTranscript
                        ) : (
                          <span className="recording-modal-transcript-placeholder">
                            {isRecording ? 'Speaking...' : 'Start recording to see live transcription'}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="recording-modal-step recording-modal-step-name">
              <h3>Name your recording</h3>
              <input
                type="text"
                value={recordingName}
                onChange={(e) => setRecordingName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSave()}
                placeholder="e.g. Call with Steve"
                autoFocus
                aria-label="Recording name"
              />
              {uploadError && <div className="recording-modal-error">{uploadError}</div>}
              <div className="recording-modal-actions">
                <button
                  type="button"
                  className="recording-modal-btn recording-modal-btn-save"
                  onClick={handleSave}
                  disabled={uploading}
                >
                  {uploading ? 'Processing...' : 'Save'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}
