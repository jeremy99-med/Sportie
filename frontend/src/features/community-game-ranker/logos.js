// Team logos live in src/assets/Logos/<League folder>/<nickname>.png.
// Vite resolves every PNG at build time; we key them by sport + nickname.
const files = import.meta.glob("../../assets/Logos/**/*.png", { eager: true, import: "default" });

const FOLDER_SPORT = { "NFL Logos": "NFL", "NBA Team Logos": "NBA" };

// Files whose name isn't the team nickname.
const FILE_ALIASES = {
  "614479b15953a50004ee16ca": "jets",
  stealers: "steelers",
};

const normalize = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

const logosBySport = {};
for (const [path, url] of Object.entries(files)) {
  const [, folder, file] = path.match(/Logos\/([^/]+)\/([^/]+)\.png$/) ?? [];
  const sport = FOLDER_SPORT[folder];
  if (!sport) continue;
  const key = normalize(FILE_ALIASES[file] ?? file);
  (logosBySport[sport] ??= {})[key] = url;
}

/** Logo URL for a team, matched by the end of its full name
 * ("Portland Trail Blazers" -> trailblazers.png). Null when there's no logo (e.g. NHL/MLB). */
export function teamLogo(sport, team) {
  const logos = logosBySport[sport];
  if (!logos || !team?.name) return null;
  const name = normalize(team.name);
  const match = Object.keys(logos)
    .filter((key) => name.endsWith(key))
    .sort((a, b) => b.length - a.length)[0];
  return match ? logos[match] : null;
}
