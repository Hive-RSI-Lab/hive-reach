# conn-imessage

Talk to the hive from iMessage's chat with yourself, on a Mac you are signed in on.

**Not tested on a Mac.** This tower is Linux, so the tests only cover the filter, the `chat.db` parsing (on a made-up database) and the spool. The real `chat.db` layout, `osascript` and ssh from the Mac are assumptions until someone runs it there.

## Read this before you start

A linked device can see all of your chats, not just one. **Only the self-chat is processed**: everything else is dropped the moment it arrives, before its text or files are stored, logged or read, and attachments from other chats are never fetched. **The code will only ever message you**: sending to any other chat is refused in code. The link session is a credential (it is as good as a logged-in device), kept in a folder only you can read and never logged. Messages the connector sends to the chat come back as echoes; they are recognised and ignored so the hive does not talk to itself.

Apple has no ban for this, but reading `chat.db` needs Full Disk Access for the terminal that runs the script, which is a wide permission on your Mac. The script opens the database read-only and selects only the one-to-one chat with your own handle.

## How it fits together

`mac_bridge.py` runs on the Mac. It connects out to the tower with ssh over tailscale (no public port, nothing listens on either side). The tower end is `spool.py`, a folder of small files that `connector.py` reads.

## Set up (your steps)

1. Put your own iMessage phone number or email in `~/.config/h2/conn/imessage.json`: `{"self": "+46701234567"}`, then `conn on imessage` once (it makes the spool folder).
2. On the Mac, make an ssh key just for this, and on the tower add it to `~/.ssh/authorized_keys` restricted to the spool, so it can do nothing else:
   `command="python3 -I ~/modules/connectors/conn-imessage/spool.py",restrict ssh-ed25519 AAAA... mac-imessage`
3. Copy `mac_bridge.py` to the Mac, give the terminal Full Disk Access, and run `python3 mac_bridge.py --self +46701234567 --host USER@YOUR-HOST`. Keep it running (launchd, if you like).

## What it can't do

Attachments (a note says one was sent, nothing is forwarded), groups, other chats, files going out. The Mac must be on and signed in. Delivery to the Mac is at most once if ssh drops mid-way.
