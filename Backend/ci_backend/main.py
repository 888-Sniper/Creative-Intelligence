"""Uvicorn entry point (parity with the legacy server CLI flags)."""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402


def _google_bearer_resolver(db_path, settings):
    """Per-job Google access tokens for the scheduler thread.

    Opens employee sessions against the same database file, so
    private sheets/drive jobs transparently refresh expired access
    tokens on schedule. Resolution failures propagate to tick(),
    which records them against the job instead of stopping others.
    """
    from ci_backend import google_oauth as goog
    from ci_backend.db import make_engine, make_session_factory
    sessions = make_session_factory(make_engine(db_path))

    def resolve(job):
        owner = (job or {}).get("owner_employee_id", "")
        with sessions() as sess:
            return goog.access_token_for(sess, owner, settings)

    return resolve


def resolve_sync_every(args, settings) -> int:
    """Scheduler cadence: explicit --sync-every wins, else the
    CREATIVE_INTEL_SYNC_EVERY environment setting (0 disables). This
    is how the Oracle systemd service (which passes no CLI flags)
    consumes the configured cadence."""
    if args.sync_every and args.sync_every > 0:
        return args.sync_every
    try:
        return max(0, int(settings.sync_every))
    except (TypeError, ValueError):
        return 0


def resolve_bind(args) -> tuple:
    """Host/port for uvicorn.run (Render-compatible, local-preserving).

    Explicit CLI flags always win. Otherwise, when the PORT environment
    variable is present (Render, and similar hosts), bind 0.0.0.0 to
    that port; without PORT keep the historical 127.0.0.1:4321 default
    so local development and the Oracle systemd units behave exactly
    as before. A malformed PORT fails closed (SystemExit, no serving).
    """
    raw_port = os.environ.get("PORT", "").strip()
    if args.port is not None:
        port = args.port
    elif raw_port:
        try:
            port = int(raw_port)
        except ValueError:
            print("error: PORT=%r is not a valid port number" % raw_port,
                  file=sys.stderr)
            raise SystemExit(2)
    else:
        port = 4321
    host = args.host or ("0.0.0.0" if raw_port else "127.0.0.1")
    return host, port


def maybe_seed_demo(db_path: str, settings, fresh: bool) -> int:
    """Seed the demo dataset on first boot of a fresh database.

    Returns the number of fixture rows inserted (0 when seeding is
    disabled or the database already existed). Callers compute
    ``fresh`` BEFORE create_app() runs migrations (which creates the
    file), so an existing database from the same running instance is
    never touched and rows cannot duplicate on restart.
    """
    if not settings.demo_seed or not fresh:
        return 0
    from ci_backend.actions import load_demo_dataset
    return load_demo_dataset(db_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--host", default=None,
                    help="bind address (default: 127.0.0.1 locally,"
                    " 0.0.0.0 when the PORT env var is set)")
    ap.add_argument("--load-fixture", action="store_true")
    ap.add_argument("--sync-every", type=int, default=0,
                    help="re-run saved connector sync jobs every N seconds"
                    " (0 disables the scheduler; otherwise"
                    " CREATIVE_INTEL_SYNC_EVERY applies)")
    args = ap.parse_args()
    host, port = resolve_bind(args)

    settings = Settings()
    db_path = args.db or str(settings.database_path)
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    if args.load_fixture:
        from ci_backend.actions import load_fixtures
        print("fixture rows: %d" % load_fixtures(db_path))
        return

    fresh = (not os.path.exists(db_path)
             or os.path.getsize(db_path) == 0)
    app = create_app(db_path, settings)
    seeded = maybe_seed_demo(db_path, settings, fresh)
    if seeded:
        print("demo seed rows: %d" % seeded)
    sync_every = resolve_sync_every(args, settings)
    if sync_every > 0:
        import threading

        from creative_intel import sync
        stop = threading.Event()
        thread = threading.Thread(
            target=sync.daemon,
            args=(db_path, sync_every, stop, None,
                  _google_bearer_resolver(db_path, settings)), daemon=True)
        thread.start()
        print("sync scheduler: every %d seconds" % sync_every)

    import uvicorn
    print("Creative Intelligence on http://%s:%d" % (host, port))
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
