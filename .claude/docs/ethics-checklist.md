# Ethics and safety checklist

From the proposal's ethical considerations. The reviewer agent checks each diff against it.

## Community Game Ranker
- [ ] Every page that shows injuries or importance scores carries a gambling disclaimer
      ("For entertainment only. Not betting advice.").
- [ ] Voting needs a logged-in user, allows one vote per (user, game, category) through a DB
      constraint, and has rate limiting or a basic anti-abuse plan for fake accounts.
- [ ] The vote endpoint uses CSRF/session auth correctly, and nothing unauthenticated can write.

## Video Analyzer
- [ ] Uploads are private to their owner, and every query filters by `request.user`.
- [ ] The upload screen shows a consent notice saying people in the video should know they're
      being analyzed.
- [ ] File validation covers type and size limits, and file names are generated server-side.
- [ ] Suggestions are framed as hints, not verdicts, because they can be wrong.
- [ ] Detection accuracy has been spot-checked across skin tones and jersey colors.

## General
- [ ] Passwords go through Django's auth system only. No custom hashing.
- [ ] No secrets in code, logs, fixtures, or commits. Keys come from env vars.
- [ ] `DEBUG` stays off outside dev, and `ALLOWED_HOSTS` stays tight.
