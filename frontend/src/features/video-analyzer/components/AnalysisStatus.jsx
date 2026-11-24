import { useEffect } from "react";
import { getUpload } from "../api.js";

// Shows a spinner while the video is analyzed, then the results.
export default function AnalysisStatus({ upload, onChange, onStartOver }) {
  useEffect(() => {
    if (upload.status !== "processing") return undefined;
    const timer = setInterval(() => getUpload(upload.id).then(onChange).catch(() => {}), 3000);
    return () => clearInterval(timer);
  }, [upload.id, upload.status, onChange]);

  if (upload.status === "processing") {
    return (
      <div className="card border-0 shadow-sm">
        <div className="card-body p-4 d-flex align-items-center gap-3" role="status">
          <div className="spinner-border text-sp-cyan" aria-hidden="true" />
          <span>Analyzing your video. This can take a few minutes...</span>
        </div>
      </div>
    );
  }

  const suggestions = upload.summary?.suggestions ?? [];
  return (
    <div className="card border-0 shadow-sm">
      <div className="card-body p-4">
        <h2 className="h5 mb-3">Top-down view</h2>
        {upload.topdown_video_url && (
          <video src={upload.topdown_video_url} controls className="w-100 rounded mb-4" />
        )}
        <h2 className="h5">Suggestions</h2>
        <p className="small text-sp-muted">
          These are hints from simple rules, not verdicts. They can be wrong.
        </p>
        {suggestions.length === 0 ? (
          <p className="text-sp-muted">No suggestions for this clip.</p>
        ) : (
          <ul className="list-group">
            {suggestions.map((s, i) => (
              <li key={i} className="list-group-item">{s.text}</li>
            ))}
          </ul>
        )}
        <button type="button" className="btn btn-outline-secondary mt-3" onClick={onStartOver}>
          Analyze another video
        </button>
      </div>
    </div>
  );
}
