# conn-email

Talk to the hive by email. It reads a mailbox over IMAP (a check every 60 seconds) and answers over SMTP. Standard library only.

**Use a mailbox made only for this. Never the person's own.** Sending from the person's own mailbox is not allowed (limit 4), and a bot mailbox keeps the blast radius small.

## Setup (the person's steps)
1. Make a new mailbox for the hive (any provider with IMAP, SMTP and an app password). Signing up is yours, not an agent's.
2. Make an app password for it and save it as the secret `conn-email` with the dashboard's lock.
3. Config (`~/.config/h2/conn/email.json`):
   - `imap_host`, `smtp_host`, `address` (the bot mailbox); optional `imap_port` (993), `smtp_port` (465, or 587 for STARTTLS), `poll` (60), `max_attachment` (bytes, default 10 MB)
   - `allow_from`: the addresses allowed to write, e.g. `["you@example.com"]`. They go through the bridge's allow-list. Anyone else who passes DKIM gets a pairing code (sent only through the bridge) that you approve on the dashboard.
   - `auth_server`: the authserv-id your mailbox's server puts at the start of its `Authentication-Results` header. Look at the header of any received mail: `Authentication-Results: mx.example.net; dkim=pass ...` means `mx.example.net`.
4. Turn it on with `conn on email`.

## How identity works
A From address is forgeable, so it is not enough. A message counts only if:
- there is exactly one From, a plain address (lowercased and used as the sender and the `chat`);
- the **first** `Authentication-Results` header (the one your own server put on top) starts with `auth_server` and has `dkim=pass` with `header.d` or `header.i` aligned to the From domain. Any other such header is ignored, since senders can add their own;
- alignment is **strict**: the DKIM domain must be exactly the From domain. A company that signs from a subdomain won't pass; say so and we'll list it.
- the message must be addressed to this mailbox (To or Cc), and a Message-ID is taken only once, so signed mail meant for someone else, or sent again, doesn't count.

Anything else is dropped: no reply, no pairing code, nothing posted. Mail is never posted as `person`; the bridge tags it `(from email)` and strips mentions.

## Behaviour
- One sender address = one board thread. Replies keep the Subject (`Re: ...`) and `In-Reply-To`/`References`.
- Replies go only to addresses that have written in with a verified DKIM pass. Every reply has `Auto-Submitted: auto-replied`.
- Ignored to avoid loops: `Auto-Submitted` (other than `no`), `List-Id`, `List-Unsubscribe`, `Precedence: bulk/list/junk`, `X-Auto-Response-Suppress`, empty Return-Path, mailer-daemon and no-reply senders, and its own address.
- Text only. `text/plain` is preferred; HTML-only mail is turned into plain text. The quoted reply tail is cut ("On ... wrote:", Original Message rules, trailing `>` lines); if that leaves nothing, the whole text is kept.
- Attachments under the size cap are saved for known senders only (allow-list or paired) and posted; bigger ones are named in the text.
- Progress is kept by UID in `~/.local/state/conn/email/state.json`. The first run starts at the newest message and does not replay history; a changed UIDVALIDITY starts again at the newest.

## Can't do
HTML formatting, IDLE (it polls), reading anything but INBOX, trusting a server whose `auth_server` you haven't set.
