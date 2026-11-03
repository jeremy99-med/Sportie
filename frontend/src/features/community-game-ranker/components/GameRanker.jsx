import { useEffect, useState } from "react";
import { getMe } from "../../../shared/auth/api.js";
import { castVote, getGames } from "../api.js";
import { dayLabel, todayEastern } from "../dates.js";
import AuthBar from "./AuthBar.jsx";
import DayPicker from "./DayPicker.jsx";
import GameCard from "./GameCard.jsx";

const SPORTS = ["NBA", "NFL"];

export default function GameRanker() {
  const [sport, setSport] = useState(SPORTS[0]);
  const [date, setDate] = useState(todayEastern);
  const [games, setGames] = useState(null); // null while the first load for this selection runs
  const [error, setError] = useState(null);
  const [user, setUser] = useState(null);
  const [votingId, setVotingId] = useState(null);
  const [voteError, setVoteError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    getMe()
      .then((me) => setUser(me.user))
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    let ignore = false; // drop the response if the selection changes before it arrives
    getGames({ date, sport })
      .then((data) => {
        if (ignore) return;
        setGames(data);
        setError(null);
      })
      .catch((err) => {
        if (!ignore) setError(err.message);
      });
    return () => {
      ignore = true;
    };
  }, [date, sport, reloadKey]);

  const reload = () => setReloadKey((key) => key + 1);

  function clearGames() {
    setGames(null);
    setError(null);
    setVoteError(null);
  }

  function selectSport(next) {
    setSport(next);
    clearGames();
  }

  function selectDate(next) {
    setDate(next);
    clearGames();
  }

  function handleAuthChange(nextUser) {
    setUser(nextUser);
    reload(); // my_vote depends on who is signed in
  }

  async function handleVote(id, value) {
    setVotingId(id);
    setVoteError(null);
    try {
      const result = await castVote(id, value);
      setGames((current) => current?.map((g) => (g.id === id ? { ...g, ...result } : g)) ?? current);
      reload(); // the server owns the ordering, and a vote can change it
    } catch (err) {
      setVoteError(err.message);
    } finally {
      setVotingId(null);
    }
  }

  return (
    <section aria-labelledby="ranker-title">
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-4">
        <div>
          <h1 id="ranker-title" className="h2 mb-2">
            {date === todayEastern() ? "Today's games" : `Games on ${dayLabel(date)}`}
          </h1>
          <div className="btn-group" role="group" aria-label="Choose a sport">
            {SPORTS.map((code) => (
              <button
                type="button"
                key={code}
                className={`btn ${code === sport ? "btn-primary" : "btn-outline-primary"}`}
                aria-pressed={code === sport}
                onClick={() => selectSport(code)}
              >
                {code}
              </button>
            ))}
          </div>
        </div>
        <AuthBar user={user} onChange={handleAuthChange} />
      </div>

      <DayPicker selected={date} onSelect={selectDate} />

      {voteError && <p className="text-sp-red" role="alert">{voteError}</p>}

      {error ? (
        <p className="text-sp-red" role="alert">Could not load games: {error}</p>
      ) : games === null ? (
        <p className="text-secondary" role="status">Loading games...</p>
      ) : games.length === 0 ? (
        <p className="text-secondary">
          No {sport} games {date === todayEastern() ? "today" : `on ${dayLabel(date)}`}.
        </p>
      ) : (
        <ol className="list-unstyled mb-0">
          {games.map((game, index) => (
            <GameCard
              key={game.id}
              game={game}
              rank={index + 1}
              canVote={Boolean(user)}
              voting={votingId === game.id}
              onVote={handleVote}
            />
          ))}
        </ol>
      )}

      <p className="small text-secondary mt-4 mb-0">For entertainment only. Not betting advice.</p>
    </section>
  );
}
