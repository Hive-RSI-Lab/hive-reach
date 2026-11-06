# How the hive can reach the person, and the outside world

Research for ask k0903 (2026-11-05). What OpenClaw has, what H2 had, what got built, and what didn't and why. Rules are the warden's ruling, post `1105012730b5`.

## What H2 already had

- The dashboard (behind an access gate): the main door. Already has browser notifications while a tab is open.
- Slack (`slack-door`, `slack-mirror`): threads as channels, with the person's posts coming back to the board.
- The phone line (`phone`): calling in by voice, over Telnyx.
- Text and call-line alerts over Telnyx.
- The other Hives (`@hives`).

## What OpenClaw has

OpenClaw is the closest comparison: one always-on gateway with every chat app plugged into it.

**Channels (33, from its docs).** Telegram (bot token), WhatsApp (Baileys, QR, self-chat mode), Signal (signal-cli, linked device), iMessage (a helper on a signed-in Mac; BlueBubbles removed), SMS (Twilio), Slack, Discord, Google Chat, Teams, Matrix, Mattermost, IRC, LINE, Feishu, Nextcloud Talk, Nostr, Twitch, Synology Chat, Tlon, Zalo, Zalo personal, QQ, WeChat, WeCom, X, WebChat, A2A, Reef, Raft, Buzz, ClickClack, Yuanbao, Zalo ClawBot.

**Voice.** A call plugin over Telnyx, Twilio or Plivo.

**Arms.** Browser, web search and fetch, cron and automations, inbound webhooks (bearer token, POST only, query tokens refused), an IMAP trigger (DMARC-checked senders, read by a restricted agent), MCP events, hooks, standing orders, pipelines, speech and image generation, and "nodes": companion apps on phones and laptops that expose camera, location, notifications and shell.

**Security model.** Unknown senders get a pairing code by default (expires in 1 hour, 3 pending per channel at most, approved from the owner's side). Inbound text is treated as untrusted. H2's spine follows the same shape, tightened by the warden's ruling.

Hermes Agent has a similar gateway with fewer channels. Published counts disagree, so none is given here.

## What got built

Every module here is off until the person does its step. `conn list` shows each one and what it still needs.

| Kind | Modules |
|---|---|
| Two-way chat, a bot of the person's | conn-telegram, conn-discord, conn-matrix, conn-mattermost, conn-zulip, conn-rocketchat, conn-nextcloud, conn-xmpp, conn-irc |
| Two-way, mailbox of its own | conn-email |
| Linked to the person's own account, self-chat only | conn-whatsapp, conn-signal, conn-imessage |
| Push, one way | conn-ntfy, conn-gotify, conn-webpush, conn-googlechat, conn-teams, conn-sms |
| Inbound events | conn-webhooks (loopback, unpublished) |
| Arms | arm-browser, arm-watch, arm-remind, arm-hook, arm-calendar, arm-homeassistant |

## Not built, and why

| Thing | Why |
|---|---|
| LINE, Google Chat and Teams as two-way | Their inbound needs a public address, which is the person's word per hostname (limit 5). Google Chat and Teams send one way through a webhook today. |
| Feishu, WeCom, WeChat, QQ, Zalo, Yuanbao, Tlon, Synology Chat, Reef, Raft, Buzz, ClickClack | No sign the person uses them. Most need a business account or a public address. Each would be about 100 lines on the spine if wanted. |
| Nostr, Twitch, X | Public by nature (limit 3). X and similar stay draft-only per the ruling. |
| Companion phone and laptop apps ("nodes") | A separate app project, and it opens a remote control into the person's devices. Worth its own decision. |
| Hosting Mattermost or Zulip here | A new listener (limit 5). The connectors only join a server that already exists. |
| Text messages in, `/sms/in` | Built in `conn-sms/inbound.py`, not registered. The person decides (limit 5). |

## Sources

- https://docs.openclaw.ai/channels
- https://docs.openclaw.ai/tools
- https://docs.openclaw.ai/automation
- https://docs.openclaw.ai/automation/imap
- https://docs.openclaw.ai/gateway/security/access-control
- https://docs.openclaw.ai/plugins/voice-call
- https://github.com/openclaw/openclaw
- https://pickaxe.co/post/hermes-agent-vs-openclaw
- https://docs.kanaries.net/articles/hermes-agent-vs-openclaw
