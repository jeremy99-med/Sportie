import { useState } from "react";
import { analyzeUpload } from "../api.js";

const CORNER_NAMES = ["top-left", "top-right", "bottom-right", "bottom-left"];

// Lets the user click the 4 court corners on the first frame, then starts the analysis.
export default function CornerPicker({ upload, onStarted }) {
  const [corners, setCorners] = useState([]);
  const [videoSize, setVideoSize] = useState(null);
  const [direction, setDirection] = useState("left_to_right");
  const [error, setError] = useState(null);
  const [starting, setStarting] = useState(false);

  function handleClick(event) {
    if (corners.length === 4 || !videoSize) return;
    const box = event.target.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * videoSize.width;
    const y = ((event.clientY - box.top) / box.height) * videoSize.height;
    setCorners([...corners, [Math.round(x), Math.round(y)]]);
  }

  async function handleStart() {
    setStarting(true);
    setError(null);
    try {
      onStarted(await analyzeUpload(upload.id, corners, direction));
    } catch (err) {
      setError(err.body?.error || err.message);
      setStarting(false);
    }
  }

  if (!upload.first_frame_url) {
    return (
      <div className="alert alert-warning">
        The server couldn't make a preview picture because the video tools aren't installed. Start
        the app with <code>just up-video</code>, then upload the video again.
      </div>
    );
  }

  return (
    <div className="card border-0 shadow-sm">
      <div className="card-body p-4">
        <h2 className="h5">
          {corners.length < 4
            ? `Click the ${CORNER_NAMES[corners.length]} corner of the court (${corners.length + 1} of 4)`
            : "All 4 corners picked"}
        </h2>

        <div className="position-relative mb-3" style={{ cursor: "crosshair" }}>
          <img
            src={upload.first_frame_url}
            alt="First frame of your video"
            className="w-100 rounded"
            onLoad={(e) => setVideoSize({ width: e.target.naturalWidth, height: e.target.naturalHeight })}
            onClick={handleClick}
          />
          {videoSize &&
            corners.map(([x, y], i) => (
              <span
                key={i}
                className="position-absolute badge rounded-pill"
                style={{
                  left: `${(x / videoSize.width) * 100}%`,
                  top: `${(y / videoSize.height) * 100}%`,
                  transform: "translate(-50%, -50%)",
                  background: "var(--sp-yellow)",
                  color: "var(--sp-bg)",
                  pointerEvents: "none",
                }}
              >
                {i + 1}
              </span>
            ))}
        </div>

        <div className="d-flex flex-wrap gap-2 align-items-center">
          <button
            type="button"
            className="btn btn-outline-secondary"
            onClick={() => setCorners([])}
            disabled={corners.length === 0}
          >
            Reset corners
          </button>
          <label htmlFor="direction" className="ms-2">Team A attacks</label>
          <select
            id="direction"
            className="form-select w-auto"
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
          >
            <option value="left_to_right">left → right</option>
            <option value="right_to_left">right → left</option>
          </select>
          <button
            type="button"
            className="btn btn-primary ms-auto"
            onClick={handleStart}
            disabled={corners.length < 4 || starting}
          >
            {starting ? "Starting..." : "Analyze video"}
          </button>
        </div>

        {error && <div className="alert alert-danger mt-3 mb-0" role="alert">{error}</div>}
      </div>
    </div>
  );
}
