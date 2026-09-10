"""Uvicorn entry point (parity with the legacy server CLI flags)."""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="")
    ap.add_argument("--port", type=int, default=4321)
    ap.add_argument("--load-fixture", action="store_true")
    ap.add_argument("--sync-every", type=int, default=0,
                    help="re-run saved connector sync jobs every N seconds"
                    " (0 disables the scheduler)")
    args = ap.parse_args()

    settings = Settings()
    db_path = args.db or str(settings.database_path)
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    if args.load_fixture:
        import server as legacy
        print("fixture rows: %d" % legacy.load_fixtures(db_path))
        return

    app = create_app(db_path, settings)
    if args.sync_every > 0:
        import threading
        from creative_intel import sync
        stop = threading.Event()
        thread = threading.Thread(
            target=sync.daemon,
            args=(db_path, args.sync_every, stop), daemon=True)
        thread.start()
        print("sync scheduler: every %d seconds" % args.sync_every)

    import uvicorn
    print("Creative Intelligence on http://127.0.0.1:%d" % args.port)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
