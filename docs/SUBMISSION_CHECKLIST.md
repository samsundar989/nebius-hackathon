# Submission run sheet (Samuel, Tue Oct 27 → Wed Oct 28)

In order. Everything here is a click or a copy-paste; nothing in it spends model money. The
deadline is **Fri Oct 30, 12:00 CDT**; the plan is to finish by Wed 21:00 CDT.

## Tuesday

**(a) History rewrite — only if your ANSWER 0012 is "yes".** Your Gmail address is the author
e-mail of every commit. Skip this step if you don't mind that.
1. GitHub → Settings → Emails → turn on "Keep my email addresses private" and copy the
   `…@users.noreply.github.com` address shown there.
2. `pip install git-filter-repo`
3. From the repo: `bash scripts/rewrite_history.sh --dry-run <noreply-address>`. It lists
   what would change and changes nothing.
4. `bash scripts/rewrite_history.sh <noreply-address>`: this rewrites a fresh clone in
   `../nebius-hackathon-rewrite` (with a backup branch) and prints checks plus one command.
5. Run the printed checks, then run the printed `git push --force origin main` yourself from
   that folder. Afterwards, re-clone or `git fetch && git reset --hard origin/main` here.

**(b) Make the repository public.** github.com/samsundar989/nebius-hackathon → Settings →
General → Danger Zone → Change repository visibility → Change to public → confirm.

**(c) Dashboard on GitHub Pages** (unless Render is already live). Settings → Pages → Build and
deployment → Source: **GitHub Actions**. Then Actions → **pages** → Run workflow (branch `main`).
When it finishes, the URL is on the run page (`https://samsundar989.github.io/nebius-hackathon/`).

**(d) Put the links in, everywhere at once.**

```
uv run python scripts/set_links.py --dashboard <dashboard-url> --video <youtube-url> --dry-run
uv run python scripts/set_links.py --dashboard <dashboard-url> --video <youtube-url> --rebuild-video
git add -A && git commit -m "Links: dashboard and video" && git push
```

It replaces the placeholders in README, DEVPOST.md and the video end card, and `--rebuild-video`
re-records the silent cut so the end card shows the dashboard. Then re-mix the narration:
`bash video/mux.sh narration.wav` (the step (f) upload uses the result).

**(e) Devpost, field by field** (text in `docs/DEVPOST.md`):

| field | paste |
|---|---|
| Project name | `Leakproof` |
| Tagline | the "Tagline" line |
| Track | Coding & Agentic Engineering |
| About the project (story) | everything from "## Inspiration" through "## What's next" |
| Built with | the "## Built with" line (comma-separated tags) |
| "Try it out" links | repository URL, dashboard URL |
| Video demo link | the YouTube URL from (f) |
| Image gallery | thumbnail first (`docs/devpost/thumbnail.png`), then images 1–6 and `architecture.png`, in the order listed under "## Gallery images" |
| Feedback question | the "## Feedback for Nebius and NVIDIA" section (full version: `docs/FEEDBACK.md`) |
| Repository | github.com/samsundar989/nebius-hackathon |

Save as draft; submit on Wednesday after (g).

**(f) YouTube.** Upload `video/leakproof_final.mp4` (from `video/mux.sh`), visibility **Public**
(or Unlisted if the rules allow). Title: `Leakproof — verified fixes for memory bugs, or nothing
(Nebius x NVIDIA hackathon)`. Description:

```
Leakproof fixes memory-safety bugs in C, C++ and CUDA and ships only the fixes an evidence gate
verifies. Nemotron 3 Ultra plans, Nemotron 3.5 Lightning writes patches, Nemotron 3 Super attacks
them; everything runs on Nebius Token Factory and the gate on Nebius Sandboxes.

Code: https://github.com/samsundar989/nebius-hackathon
Dashboard: <dashboard-url>
```

Subtitles: YouTube Studio → Subtitles → Add language English → Upload file → "With timing" →
`video/captions.srt`.

## Wednesday

**(g) Final pass, then tag.**
1. `uv run python scripts/readme_numbers.py` and check `git diff docs/NUMBERS.md` is empty or
   only the spend line; if a README/DEVPOST number changed, fix it there too.
2. Open the dashboard, the README and the video in a private browser window (logged out): every
   link works, the video plays, the dashboard loads.
3. `git tag v1.0-submission && git push origin v1.0-submission`
4. Devpost → Submit. Freeze: no pushes after 21:00 CDT.
