# conn-googlechat

Post a short note into a Google Chat space. Outgoing only; `pings` is `short` by default, so it says only that something is waiting.

Set up (your steps):
1. In the space: Apps & integrations > Webhooks > add one, copy its URL.
2. Save the URL itself as `conn-googlechat` with the dashboard's lock (it holds its own key, so treat it like a password).

Can't receive. Inbound would need a public address for Google to call, so it is not built; publishing one is your word per hostname. Everyone in the space sees what is posted.
