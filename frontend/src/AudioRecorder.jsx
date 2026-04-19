import { useState, useRef, useCallback } from 'react';

export function AudioRecorder({ onRecordingReady, disabled }) {
  const [isRecording, setIsRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const durationRef = useRef(0);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        if (chunksRef.current.length > 0) {
          const blob = new Blob(chunksRef.current, { type: mimeType });
          const durationSec = durationRef.current;
          onRecordingReady(blob, durationSec);
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
  }, [onRecordingReady]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setIsRecording(false);
  }, []);

  const formatTime = (sec) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="recorder">
      {isRecording ? (
        <>
          <div className="recording-indicator">
            <span className="pulse" /> Recording {formatTime(duration)}
          </div>
          <button className="btn btn-danger" onClick={stopRecording}>
            Stop Recording
          </button>
        </>
      ) : (
        <button
          className="btn btn-primary"
          onClick={startRecording}
          disabled={disabled}
        >
          Start Recording
        </button>
      )}
    </div>
  );
}
