# HUMAN — questions for Samuel and his answers

Builder (Claude Code) appends `## QUESTION NNNN` blocks. Samuel answers with `## ANSWER NNNN` blocks. Builder takes a sensible default and continues unless the question is about money, licensing, or something irreversible.

## QUESTION 0001 — AI Cloud billing status (needed before kickoff step 3.7)
Has the Nebius AI Cloud card been added and the $25 top-up landed as balance? Do the eu-north1 quotas show L40S > 0 and preemptible VMs > 0? (Console → Administration → Limits → Quotas.) Reply with ANSWER 0001.

## QUESTION 0002 — Sandboxes beta
Has the Sandboxes beta request been approved (does `GET /sandboxes/v1/whoami` return 200)? If still 403 after 24 h, please post in the Nebius Discord Sandboxes channel and email contree@nebius.com mentioning the Devpost hackathon. Reply with ANSWER 0002 when it changes.
