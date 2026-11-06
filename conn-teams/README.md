# conn-teams

Post a short note into a Microsoft Teams channel. Outgoing only; `pings` is `short` by default, so it says only that something is waiting.

Set up (your steps):
1. In Teams, use Workflows: "Post to a channel when a webhook request is received", pick the channel, copy the URL.
2. Save the URL itself as `conn-teams` with the dashboard's lock (it holds its own signature, so treat it like a password).

Teams' Workflows webhooks take an Adaptive Card in a `{"type": "message", "attachments": [...]}` envelope; this sends that. The older Office 365 connector format (`{"text": ...}`) is retired and not used.

Can't receive. Inbound would need a public address for Teams to call, so it is not built; publishing one is your word per hostname. Everyone in the channel sees what is posted.
