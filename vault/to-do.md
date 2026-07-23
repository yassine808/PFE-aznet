---
tags: [pfe, backlog, planned]
type: backlog
priority: medium
status: current
---

# TO-DO

Raw backlog, unscoped to sprints yet — cross-check against [[project-overview]] sprint timeline before treating any item as committed for the current week.

- Keep the 15s (cron/interval), and add another cron task that runs at the end of the day, assembling all transcriptions + photos + messages into a simple report (+ downloadable .docx if possible + sent to email as well)
- Treat voice messages and forwarded audios the same
- Save each audio with its specific transcription in the admin dashboard
- Add error logs that log all kinds of errors
- Add settings in the dashboard to change the timer of cron triggers + email, plus another panel just for APIs and their uptime/usage etc.
- Add stats: for each day, give the % of spoken darija words vs french
- Add another free API model able to generate images based on the report etc.
- Add some solutions or critical things to be aware of
- The chatbot should know the boss's WhatsApp number / Telegram account, so it acts differently than with employees, etc. (add in settings so this can be changed)
- Add security so only employees and the director can use/talk with the assistant — if an outsider tries to talk to it, it should send one automated message pointing to HR numbers/info + contact
- Add weekly/monthly rollup report — trends across chantiers (materials used, recurring issues), useful for chef de chantier
- Add manual correction in dashboard — let manager edit/fix an extracted field if the AI got it wrong, without touching the Sheet directly
- Low-confidence STT → explicit flag for manual review in the dashboard (not just a backend log)
- Show accuracy % on each transcription in the dashboard
- Add a GitHub-style contribution heatmap in the admin dashboard — daily activity per technician (report count per day, colored by intensity) to visualize active/inactive days

## Related Notes

- [[project-overview]]
- [[architecture]]
