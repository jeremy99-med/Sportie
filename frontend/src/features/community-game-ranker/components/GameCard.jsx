import { teamLogo } from "../logos";

const STATUS_LABELS = {
  scheduled: "Scheduled",
  in_progress: "Live",
  final: "Final",
  delayed: "Delayed",
  postponed: "Postponed",
};

function startTime(iso) {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  });
}

function TeamLogo({ sport, team }) {
  const src = teamLogo(sport, team);
  if (!src) return null;
  // Decorative: the team name is printed right next to it.
  return <img src={src} alt="" width={32} height={32} className="flex-shrink-0" style={{ objectFit: "contain" }} />;
}

export default function GameCard({ game, rank, canVote, voting, onVote }) {
  const { home_team: home, away_team: away } = game;
  const matchup = `${away.name} at ${home.name}`;
  const showScore = game.status !== "scheduled" && game.home_score !== null && game.away_score !== null;

  const voteButton = (value, symbol, label) => (
    <button
      type="button"
      className={`btn btn-sm ${game.my_vote === value ? "btn-primary" : "btn-outline-primary"}`}
      aria-label={`${label} ${matchup}`}
      aria-pressed={game.my_vote === value}
      disabled={!canVote || voting}
      onClick={() => onVote(game.id, value)}
    >
      {symbol}
    </button>
  );

  return (
    <li className="card mb-3">
      <div className="card-body d-flex flex-wrap align-items-center gap-3">
        <span className="h4 mb-0 text-sp-muted" aria-label={`Rank ${rank}`}>
          {rank}
        </span>
        <div className="flex-grow-1">
          <h2 className="h5 mb-1 d-flex flex-wrap align-items-center gap-2">
            <TeamLogo sport={game.sport} team={away} />
            <span>{away.name}</span>
            <span className="text-secondary fw-normal">at</span>
            <TeamLogo sport={game.sport} team={home} />
            <span>{home.name}</span>
          </h2>
          <p className="mb-0 text-secondary small">
            <span className="badge text-bg-light me-2">{STATUS_LABELS[game.status] ?? game.status}</span>
            {showScore ? `${away.abbreviation} ${game.away_score} - ${home.abbreviation} ${game.home_score}` : startTime(game.scheduled_at)}
          </p>
        </div>
        <div className="text-center">
          <div className="h4 mb-0 text-sp-yellow">{game.importance_score ?? "—"}</div>
          <div className="small text-secondary">Importance</div>
        </div>
        <div className="d-flex align-items-center gap-2">
          {voteButton(1, "▲", "Upvote")}
          <span aria-label={`Net votes: ${game.net_votes}`}>{game.net_votes}</span>
          {voteButton(-1, "▼", "Downvote")}
        </div>
        {game.ai && (
          <p className="w-100 mb-0 small text-secondary border-top pt-2">
            <span className="text-sp-cyan fw-semibold me-1">
              AI Insight:
            </span>
            {game.ai.reason}
          </p>
        )}
      </div>
    </li>
  );
}
