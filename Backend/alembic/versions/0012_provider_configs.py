"""Admin-managed single-active provider (configs, model cache, selection).

Additive tables only; existing tables are untouched:

- ``provider_configs``: one row per canonical generation provider
  (seeded below with secret_enc NULL — nothing is configured until
  an admin saves a secret).
- ``provider_model_cache``: offered-model catalog per provider from
  the last successful discovery refresh (PK(provider_id, model_id)).
- ``active_provider_selection``: singleton row (id=1) with the active
  (provider_id, model_id) plus an optimistic-concurrency revision.
  No row (or NULL ids) means paused: live inference refuses with an
  honest "not configured" error instead of racing legacy providers.

Secrets are Fernet tokens (see ci_backend.token_crypto); this
migration only stores NULLs. Timestamps are ISO-8601 UTC text, the
repo-wide convention for sqlite datetime columns.
"""

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# Canonical seed rows: (provider_id, display, kind, base_url).
# Mirrors creative_intel.provider_inventory GENERATION_IDS; kept
# inline (not imported) so the migration stays self-contained and
# rerunnable even if the inventory module later changes.
_SEED = (
    ("gemini", "Gemini", "api_key", None),
    ("groq", "Groq", "api_key", None),
    ("muse", "Meta Muse", "api_key", None),
    ("openai", "OpenAI", "api_key", None),
    ("anthropic", "Claude", "api_key", None),
    ("deepseek", "DeepSeek", "api_key", None),
    ("kimi", "Kimi", "api_key", None),
    ("grok", "Grok", "api_key", None),
    ("qwen", "Qwen", "api_key", None),
    ("glm", "GLM", "api_key", None),
    ("openrouter", "OpenRouter", "api_key", None),
    ("nvidia", "NVIDIA", "api_key", None),
    ("teamorouter", "TeamoRouter", "api_key", None),
    ("chatgpt", "ChatGPT (Codex)", "subscription", None),
    ("ollama", "Ollama", "local", "http://127.0.0.1:11434"),
    ("litellm", "LiteLLM Proxy", "gateway", None),
    ("opencode", "OpenCode", "local", None),
)


def _tables(bind):
    return set(bind.dialect.get_table_names(bind))


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op

    bind = op.get_bind()
    names = _tables(bind)
    if "provider_configs" not in names:
        op.create_table(
            "provider_configs",
            sa.Column("provider_id", sa.Text(), primary_key=True),
            sa.Column("display", sa.Text(), nullable=False,
                      server_default=""),
            sa.Column("kind", sa.Text(), nullable=False, server_default=""),
            sa.Column("base_url", sa.Text(), nullable=True),
            sa.Column("secret_enc", sa.Text(), nullable=True),
            sa.Column("secret_updated_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False,
                      server_default=""),
            sa.Column("updated_at", sa.Text(), nullable=False,
                      server_default=""),
        )
    if "provider_model_cache" not in names:
        op.create_table(
            "provider_model_cache",
            sa.Column("provider_id", sa.Text(), primary_key=True),
            sa.Column("model_id", sa.Text(), primary_key=True),
            sa.Column("display", sa.Text(), nullable=False,
                      server_default=""),
            sa.Column("offered", sa.Integer(), nullable=False,
                      server_default="1"),
            sa.Column("fetched_at", sa.Text(), nullable=False,
                      server_default=""),
        )
    if "active_provider_selection" not in names:
        op.create_table(
            "active_provider_selection",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider_id", sa.Text(), nullable=True),
            sa.Column("model_id", sa.Text(), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False,
                      server_default="1"),
            sa.Column("updated_by", sa.Text(), nullable=False,
                      server_default=""),
            sa.Column("updated_at", sa.Text(), nullable=False,
                      server_default=""),
            sa.CheckConstraint("id = 1",
                               name="ck_active_provider_singleton"),
        )
    # Seed configs idempotently; never touch existing rows (an admin
    # secret must survive re-upgrade).
    now = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat()
    for pid, display, kind, base in _SEED:
        bind.exec_driver_sql(
            "INSERT OR IGNORE INTO provider_configs "
            "(provider_id, display, kind, base_url, secret_enc,"
            " secret_updated_at, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
            (pid, display, kind, base, now, now))
    # No active-selection seed: NULL (missing row) means paused.


def downgrade() -> None:
    from alembic import op

    bind = op.get_bind()
    names = _tables(bind)
    if "active_provider_selection" in names:
        op.drop_table("active_provider_selection")
    if "provider_model_cache" in names:
        op.drop_table("provider_model_cache")
    if "provider_configs" in names:
        op.drop_table("provider_configs")
