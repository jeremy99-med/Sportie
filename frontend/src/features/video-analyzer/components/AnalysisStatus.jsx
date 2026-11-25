import { useEffect, useRef } from "react";
import { getUpload } from "../api.js";

// Shows a spinner while the video is analyzed, then the results.
export default function AnalysisStatus({ upload, onChange, onStartOver }) {
  const videoRef = useRef(null);

  useEffect(() => {
    if (upload.status !== "processing") return undefined;
    const timer = setInterval(() => getUpload(upload.id).then(onChange).catch(() => {}), 3000);
    return () => clearInterval(timer);
  }, [upload.id, upload.status, onChange]);

  function jumpTo(seconds) {
    videoRef.current.currentTime = seconds;
    videoRef.current.play();
  }

  const startOverButton = (
    <button type="button" className="btn btn-outline-secondary mt-3" onClick={onStartOver}>
      Analyze another video
    </button>
  );

  if (upload.status === "processing") {
    return (
      <div className="card border-0 shadow-sm">
        <div className="card-body p-4 d-flex align-items-center gap-3" role="status">
          <div className="spinner-border text-sp-cyan" aria-hidden="true" />
          <span>Analyzing your video. This takes about a minute...</span>
        </div>
      </div>
    );
  }

  if (upload.status === "failed") {
    return (
      <div>
        <div className="alert alert-danger mb-0" role="alert">
          The analysis failed: {upload.error}
        </div>
        {startOverButton}
      </div>
    );
  }

  const suggestions = upload.summary?.suggestions ?? [];
  return (
    <div className="card border-0 shadow-sm">
      <div className="card-body p-4">
        <h2 className="h5 mb-3">Top-down view</h2>
        {upload.topdown_video_url && (
          <video
            ref={videoRef}
            src={upload.topdown_video_url}
            className="w-100 rounded"
            autoPlay
            muted
            loop
            playsInline
            controls
          />
        )}
        <p className="small text-sp-muted mt-2 mb-4">🔴 Team A · 🔵 Team B · 🟡 Ball</p>

        <h2 className="h5">Suggestions</h2>
        <p className="small text-sp-muted">
          These are hints from simple rules, not verdicts. They can be wrong. Click one to jump to it.
        </p>
        {suggestions.length === 0 ? (
          <p className="text-sp-muted">No suggestions for this clip.</p>
        ) : (
          <div className="list-group">
            {suggestions.map((s, i) => (
              <button
                key={i}
                type="button"
                className="list-group-item list-group-item-action"
                onClick={() => jumpTo(s.time ?? 0)}
              >
                {s.text}
              </button>
            ))}
          </div>
        )}
        {startOverButton}
      </div>
    </div>
  );
}
