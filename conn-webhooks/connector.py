"""Webhooks as `conn` sees them: listed and checked, never started. The receiver is its own unit, because it's a listening port and the
bridge's rule is that connectors connect outwards. `ready` is never empty, so `conn on webhooks` refuses and says what to do instead."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "conn")); sys.path.insert(0, str(HERE))
import conn as C
import webhook_receiver as R


class Webhooks(C.Connector):
    name = "webhooks"; label = "Webhooks"; size = 0; can_receive = False

    def ready(self):
        try: R.parse_config(self.cfg)
        except ValueError as e: return str(e)
        return "runs from its own unit, not `conn on`: see the module's README"

    def send(self, chat, text, files=()):
        raise PermissionError("webhooks only come in; nothing goes out this way")


CONNECTOR = Webhooks
