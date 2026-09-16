import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { api, ApiError } from "@/api/client";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import {
  EmptyState,
  PageHeader,
  Panel,
  Skeleton,
  Switch,
  Toast,
} from "@/components/product";
import { useLocale } from "@/i18n";

/** Admin single-active-provider management.
 *
 * Server-driven throughout: the provider list, active selection,
 * revision, cache stats and unsupported entries all come from
 * GET /api/admin/providers — nothing is hardcoded. Secrets are
 * write-only: inputs start empty, are never prefilled, and are
 * cleared on submit. Save/test/refresh never change activation;
 * only the Activate radio and Deactivate button do (both confirm).
 */

interface ProviderEntry {
  provider_id: string;
  display: string;
  kind: string;
  supported: boolean;
  unsupported_reason?: string | null;
  base_url?: string | null;
  has_secret: boolean;
  secret_updated_at?: string | null;
  configured: boolean;
  models_cached: number;
  offered_count: number;
  fetched_at?: string | null;
  stale: boolean;
  cached_models?: OfferedModel[] | null;
}

interface ActiveSelection {
  provider_id: string;
  model_id: string;
  revision: number;
  updated_by?: string;
  updated_at?: string;
  /** Video-workflow support for the exact active id (item 32):
   *  eligible only when verified native-video capable. Absent on
   *  older backends — UI treats that as unverified. */
  support?: string;
  video_eligible?: boolean;
  support_doc?: string | null;
}

interface ProvidersList {
  providers: ProviderEntry[];
  active: ActiveSelection | null;
  current_revision: number;
}

interface OfferedModel {
  id: string;
  label?: string;
  support?: string;
  video_eligible?: boolean;
  support_doc?: string | null;
}

/** Localized video-workflow support level (item 32). Unknown or
 *  absent levels render as unverified — never as capable. */
export function supportLabel(t: (key: string) => string, level?: string | null): string {
  switch (level) {
    case "native-video": return t("providers.videoLevels.nativeVideo");
    case "image": return t("providers.videoLevels.image");
    case "audio": return t("providers.videoLevels.audio");
    case "text-only": return t("providers.videoLevels.textOnly");
    default: return t("providers.videoLevels.unverified");
  }
}

interface TestResult {
  ok: boolean;
  provider_id: string;
  latency_ms: number;
  offered_count: number;
  offered: OfferedModel[];
}

type RetryAction =
  | { kind: "activate"; providerId: string; modelId: string }
  | { kind: "deactivate" };

const LIST_TIMEOUT_MS = 15000;
const MUTATION_TIMEOUT_MS = 45000;
const PROBE_TIMEOUT_MS = 60000;

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function isConflict(e: unknown): boolean {
  return e instanceof ApiError && e.status === 409;
}

function isAbort(e: unknown): boolean {
  return (
    (typeof DOMException !== "undefined" && e instanceof DOMException && e.name === "AbortError") ||
    (e instanceof Error && e.name === "AbortError")
  );
}

/** Small hover/focus tooltip (WorkbookPage FocusTip pattern). */
function FocusTip({ label, children }: { label: string; children: React.ReactNode }) {
  const [show, setShow] = useState(false);
  return (
    <span className="trend-tooltip-anchor"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}>
      {children}
      {show ? <span className="kpi-tip" role="status">{label}</span> : null}
    </span>
  );
}

function Badge({ tone, children }: { tone: "active" | "muted" | "warn"; children: React.ReactNode }) {
  /* Status badges (Configured / Not Configured / Active) share the
   * Apply Filters teal family with white text; the Stale Catalog
   * warning keeps its amber semantics. */
  const status = tone !== "warn";
  const bg = status ? "var(--shell-teal-dark)" : "var(--shell-amber-soft)";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      fontSize: 11.5, fontWeight: 700, letterSpacing: ".03em",
      background: bg, color: status ? "#fff" : "var(--shell-navy)",
      border: "1px solid var(--shell-line)", borderRadius: 999,
      padding: "3px 10px", whiteSpace: "nowrap",
    }}>
      {children}
    </span>
  );
}

export function ProvidersPage() {
  const { t, fmtDate } = useLocale();
  const [data, setData] = useState<ProvidersList | null>(null);
  const [loadError, setLoadError] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const [conflict, setConflict] = useState<{ message: string; action: RetryAction } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const closeToast = useCallback(() => setToast(null), []);
  const dataRef = useRef<ProvidersList | null>(null);
  dataRef.current = data;

  const reload = useCallback(async (signal?: AbortSignal): Promise<ProvidersList | null> => {
    const res = await api<ProvidersList>("GET", "/api/admin/providers", undefined, {
      timeoutMs: LIST_TIMEOUT_MS, signal,
    });
    setData(res);
    setLoadError("");
    return res;
  }, []);

  useEffect(() => {
    let live = true;
    const ctrl = new AbortController();
    reload(ctrl.signal).catch((e: unknown) => {
      if (!live || isAbort(e)) return;
      setLoadError(msg(e) || t("providers.errors.loadFailed"));
    });
    return () => {
      live = false;
      ctrl.abort();
    };
  }, [reload, t]);

  const refreshQuiet = useCallback(async () => {
    try {
      await reload();
      setToast(t("providers.notices.listRefreshed"));
    } catch (e) {
      if (!isAbort(e)) setLoadError(msg(e) || t("providers.errors.loadFailed"));
    }
  }, [reload, t]);

  const fail409 = useCallback(async (e: unknown, action: RetryAction) => {
    const message = msg(e) || t("providers.notices.conflict");
    // The selection moved under us: refetch first so the retry
    // below runs against the fresh revision.
    try {
      await reload();
    } catch {
      /* retry still runs against the last-known revision */
    }
    setConflict({ message, action });
  }, [reload, t]);

  const runActivate = useCallback(async (
    providerId: string, modelId: string, revision: number,
  ): Promise<void> => {
    const key = `activate:${providerId}`;
    setBusy(key);
    try {
      await api("POST", "/api/admin/providers/activate", {
        provider_id: providerId, model_id: modelId, revision,
      }, { timeoutMs: MUTATION_TIMEOUT_MS });
      await reload();
      const disp = dataRef.current?.providers.find((p) => p.provider_id === providerId)?.display ?? providerId;
      setConflict(null);
      setToast(t("providers.notices.activated", { provider: disp, model: modelId }));
    } catch (e) {
      if (isConflict(e)) await fail409(e, { kind: "activate", providerId, modelId });
      else throw e;
    } finally {
      setBusy((cur) => (cur === key ? null : cur));
    }
  }, [fail409, reload, t]);

  const runDeactivate = useCallback(async (revision: number): Promise<void> => {
    setBusy("deactivate");
    try {
      await api("POST", "/api/admin/providers/deactivate", { revision }, {
        timeoutMs: MUTATION_TIMEOUT_MS,
      });
      await reload();
      setConflict(null);
      setToast(t("providers.notices.deactivated"));
    } catch (e) {
      if (isConflict(e)) await fail409(e, { kind: "deactivate" });
      else throw e;
    } finally {
      setBusy((cur) => (cur === "deactivate" ? null : cur));
    }
  }, [fail409, reload, t]);

  const retryConflict = useCallback(() => {
    const c = conflict;
    if (!c || busy) return;
    const revision = dataRef.current?.current_revision ?? 0;
    setConflict(null);
    if (c.action.kind === "activate") {
      void runActivate(c.action.providerId, c.action.modelId, revision).catch((e: unknown) => {
        if (!isConflict(e)) setConflict({ message: msg(e), action: c.action });
      });
    } else {
      void runDeactivate(revision).catch((e: unknown) => {
        if (!isConflict(e)) setConflict({ message: msg(e), action: c.action });
      });
    }
  }, [busy, conflict, runActivate, runDeactivate]);

  if (data === null && !loadError) {
    return (
      <>
        <PageHeader title={t("providers.title")} sub={t("providers.sub")} />
        <span className="sr-only" role="status">{t("providers.loading")}</span>
        <Skeleton height={92} />
        <div style={{ height: 12 }} aria-hidden="true" />
        <Skeleton height={220} />
        <div style={{ height: 12 }} aria-hidden="true" />
        <Skeleton height={220} />
      </>
    );
  }

  if (data === null) {
    return (
      <>
        <PageHeader title={t("providers.title")} sub={t("providers.sub")} />
        <EmptyState
          icon="info"
          title={t("providers.errors.loadFailed")}
          text={loadError}
          verbatim
          action={(
            <button type="button" className="btn-outline" onClick={() => void refreshQuiet()}>
              <Icon name="reset" size={14} /> {t("common.retry")}
            </button>
          )}
        />
      </>
    );
  }

  const active = data.active;
  const activeEntry = active
    ? data.providers.find((p) => p.provider_id === active.provider_id) ?? null
    : null;
  const activeName = activeEntry?.display ?? active?.provider_id ?? "";

  return (
    <>
      <PageHeader
        title={t("providers.title")}
        sub={t("providers.sub")}
        actions={(
          <button type="button" className="btn-outline" onClick={() => void refreshQuiet()}>
            <Icon name="reset" size={14} /> {t("providers.refreshList")}
          </button>
        )}
      />
      {toast ? <Toast message={toast} onClose={closeToast} /> : null}
      {conflict ? (
        <div className="panel" role="alert" style={{ borderColor: "var(--shell-amber)" }}>
          <p style={{ margin: "0 0 10px", fontSize: 13.5, lineHeight: 1.55 }}>{conflict.message}</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button type="button" className="btn-primary" disabled={busy !== null}
              onClick={retryConflict}>
              <Icon name="reset" size={14} /> {t("providers.notices.conflictRetry")}
            </button>
            <button type="button" className="btn-outline" onClick={() => setConflict(null)}>
              {t("common.close")}
            </button>
          </div>
        </div>
      ) : null}
      {active ? (
        <Panel
          icon="spark"
          tint="var(--shell-green-soft)"
          title={t("providers.bannerActiveTitle", { provider: activeName, model: active.model_id })}
          sub={t("providers.bannerActiveSub", {
            date: active.updated_at ? fmtDate(active.updated_at) : "—",
          })}
        >
          {active.video_eligible === false ? (
            <p className="panel-sub" role="status" style={{ margin: "8px 0 0" }}>
              {t("providers.videoNotEligible", {
                model: active.model_id,
                support: supportLabel(t, active.support),
              })}
              {active.support_doc ? (
                <>
                  {" "}
                  <a href={active.support_doc} target="_blank" rel="noreferrer">
                    {t("providers.videoDocs")}
                  </a>
                </>
              ) : null}
            </p>
          ) : null}
        </Panel>
      ) : (
        <Panel
          icon="info"
          tint="var(--shell-amber-soft)"
          title={t("providers.bannerPausedTitle")}
          sub={t("providers.bannerPausedBody")}
        >{null}</Panel>
      )}
      {data.providers.length === 0 ? (
        <EmptyState
          icon="info"
          title={t("providers.errors.loadFailed")}
          text=""
        />
      ) : (
        <div role="radiogroup" aria-label={t("providers.title")}
          style={{ display: "grid", gap: 12 }}>
          {data.providers.map((entry) => (
            <ProviderCard
              key={entry.provider_id}
              entry={entry}
              active={active}
              activeName={activeName}
              revision={data.current_revision}
              busy={busy}
              setBusy={setBusy}
              onReload={reload}
              onToast={setToast}
              onConflict={fail409}
              onActivate={runActivate}
              onDeactivate={runDeactivate}
            />
          ))}
        </div>
      )}
    </>
  );
}

function ProviderCard({ entry, active, activeName, revision, busy, setBusy, onReload, onToast, onConflict, onActivate, onDeactivate }: {
  entry: ProviderEntry;
  active: ActiveSelection | null;
  activeName: string;
  revision: number;
  busy: string | null;
  setBusy: Dispatch<SetStateAction<string | null>>;
  onReload: () => Promise<ProvidersList | null>;
  onToast: (message: string) => void;
  onConflict: (e: unknown, action: RetryAction) => Promise<void>;
  onActivate: (providerId: string, modelId: string, revision: number) => Promise<void>;
  onDeactivate: (revision: number) => Promise<void>;
}) {
  const { t, tp, fmtDate } = useLocale();
  const id = entry.provider_id;
  const isActive = active?.provider_id === id;
  const needsKey = entry.kind !== "local";
  const needsBase = entry.kind === "gateway" || entry.kind === "local";
  // Display names for connection kinds; model IDs and provider names
  // are never translated.
  const kindLabel = (kind: string): string => {
    switch (kind) {
      case "api_key": return t("providers.kindApiKey");
      case "subscription": return t("providers.kindSubscription");
      case "local": return t("providers.kindLocal");
      case "gateway": return t("providers.kindGateway");
      default: return kind;
    }
  };

  // Local form state only: unsaved edits never affect routing and are
  // cleared on submit. The whole tree remounts on account change
  // (router KeyedLayout), so nothing survives a switch.
  const [keyInput, setKeyInput] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [baseUrl, setBaseUrl] = useState(entry.base_url ?? "");
  const [offered, setOffered] = useState<OfferedModel[] | null>(null);
  const [modelSearch, setModelSearch] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [cardError, setCardError] = useState("");
  const [testBusy, setTestBusy] = useState(false);
  const [testResult, setTestResult] = useState<{ ms: number; count: number } | null>(null);
  const [testError, setTestError] = useState("");
  const [refreshError, setRefreshError] = useState("");
  const testCtrl = useRef<AbortController | null>(null);
  const testWrapRef = useRef<HTMLSpanElement | null>(null);
  const modelSearchRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => () => {
    testCtrl.current?.abort();
  }, []);

  // Preselect the running model on the active card once its offered
  // list is known; never overwrite an explicit pick.
  useEffect(() => {
    if (!isActive || selectedModel || !offered || !active) return;
    if (offered.some((m) => m.id === active.model_id)) setSelectedModel(active.model_id);
  }, [isActive, offered, selectedModel, active]);

  // Seed the selector from the last-known server catalog so Refresh
  // Models visibly refreshes the options; a later Test Connection
  // replaces them with a live probe until the next reload.
  const cacheStamp = entry.fetched_at ?? "";
  useEffect(() => {
    setOffered(entry.cached_models?.length ? entry.cached_models : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, cacheStamp]);

  if (!entry.supported) {
    return (
      <Panel
        icon="lock"
        title={entry.display}
        sub={t("providers.unsupportedTitle")}
        action={<Badge tone="muted">{t("providers.unsupportedTitle")}</Badge>}
      >
        <p className="panel-sub" style={{ margin: 0 }}>{entry.unsupported_reason ?? ""}</p>
      </Panel>
    );
  }

  const filtered = (offered ?? []).filter((m) => {
    const q = modelSearch.trim().toLowerCase();
    if (!q) return true;
    return m.id.toLowerCase().includes(q) || (m.label ?? "").toLowerCase().includes(q);
  });
  const selectedVisible = selectedModel !== "" && filtered.some((m) => m.id === selectedModel);
  const selectedMeta = (offered ?? []).find((m) => m.id === selectedModel) ?? null;

  async function saveKey(): Promise<void> {
    if (busy) return;
    if (!keyInput.trim()) {
      setCardError(t("providers.keyRequired"));
      return;
    }
    const key = `save:${id}`;
    setBusy(key);
    setCardError("");
    try {
      await api(`PUT`, `/api/admin/providers/${encodeURIComponent(id)}`, {
        secret: keyInput.trim(),
      }, { timeoutMs: MUTATION_TIMEOUT_MS });
      setKeyInput("");
      setShowKey(false);
      await onReload();
      onToast(t("providers.notices.saved", { provider: entry.display }));
    } catch (e) {
      if (isConflict(e)) await onConflict(e, { kind: "deactivate" });
      else setCardError(msg(e));
    } finally {
      setBusy((cur) => (cur === key ? null : cur));
    }
  }

  async function saveBase(): Promise<void> {
    if (busy) return;
    if (!baseUrl.trim()) {
      setCardError(t("providers.baseUrlRequired"));
      return;
    }
    const key = `save-base:${id}`;
    setBusy(key);
    setCardError("");
    try {
      await api(`PUT`, `/api/admin/providers/${encodeURIComponent(id)}`, {
        base_url: baseUrl.trim(),
      }, { timeoutMs: MUTATION_TIMEOUT_MS });
      await onReload();
      onToast(t("providers.notices.baseSaved", { provider: entry.display }));
    } catch (e) {
      if (isConflict(e)) await onConflict(e, { kind: "deactivate" });
      else setCardError(msg(e));
    } finally {
      setBusy((cur) => (cur === key ? null : cur));
    }
  }

  async function removeKey(): Promise<void> {
    if (busy) return;
    const confirmMsg = isActive && active
      ? t("providers.confirms.removeKeyActive", { provider: entry.display, model: active.model_id })
      : t("providers.confirms.removeKey", { provider: entry.display });
    if (!window.confirm(confirmMsg)) return;
    const key = `remove:${id}`;
    setBusy(key);
    setCardError("");
    try {
      // Clearing the active secret atomically deactivates (backend);
      // the refetch below picks up the paused selection.
      await api(`PUT`, `/api/admin/providers/${encodeURIComponent(id)}`, {
        secret: "", confirm: true,
      }, { timeoutMs: MUTATION_TIMEOUT_MS });
      setKeyInput("");
      setShowKey(false);
      await onReload();
      onToast(t("providers.notices.removed", { provider: entry.display }));
    } catch (e) {
      if (isConflict(e)) await onConflict(e, { kind: "deactivate" });
      else setCardError(msg(e));
    } finally {
      setBusy((cur) => (cur === key ? null : cur));
    }
  }

  async function runTest(): Promise<void> {
    if (testBusy) return;
    testCtrl.current?.abort();
    const ctrl = new AbortController();
    testCtrl.current = ctrl;
    setTestBusy(true);
    setTestError("");
    setTestResult(null);
    try {
      const res = await api<TestResult>("POST", `/api/admin/providers/${encodeURIComponent(id)}/test`, {}, {
        timeoutMs: PROBE_TIMEOUT_MS, signal: ctrl.signal,
      });
      // Read-only w.r.t. activation: only the offered list feeds the
      // model selector; nothing here touches the active selection.
      setOffered(res.offered ?? []);
      setTestResult({ ms: res.latency_ms, count: res.offered_count });
    } catch (e) {
      if (isAbort(e) || ctrl.signal.aborted) setTestError(t("providers.errors.testCancelled"));
      else setTestError(msg(e));
    } finally {
      if (testCtrl.current === ctrl) testCtrl.current = null;
      setTestBusy(false);
    }
  }

  function cancelTest(): void {
    testCtrl.current?.abort();
    testWrapRef.current?.querySelector("button")?.focus();
  }

  async function runRefresh(): Promise<void> {
    if (busy || testBusy) return;
    const key = `refresh:${id}`;
    setBusy(key);
    setRefreshError("");
    try {
      await api("POST", `/api/admin/providers/${encodeURIComponent(id)}/refresh`, {}, {
        timeoutMs: PROBE_TIMEOUT_MS,
      });
      await onReload();
      onToast(t("providers.notices.refreshed", { provider: entry.display }));
    } catch (e) {
      if (isConflict(e)) await onConflict(e, { kind: "deactivate" });
      else setRefreshError(msg(e));
    } finally {
      setBusy((cur) => (cur === key ? null : cur));
    }
  }

  function requestActivate(): void {
    if (isActive || busy) return;
    if (!selectedModel) {
      setCardError(t("providers.activateNeedsModel", { provider: entry.display }));
      modelSearchRef.current?.focus();
      return;
    }
    const next = `${entry.display} (${selectedModel})`;
    const confirmMsg = active
      ? t("providers.confirms.activate", { current: `${activeName} (${active.model_id})`, next })
      : t("providers.confirms.activateFirst", { provider: entry.display, model: selectedModel });
    if (!window.confirm(confirmMsg)) return;
    setCardError("");
    void onActivate(id, selectedModel, revision).catch((e: unknown) => {
      if (!isConflict(e)) setCardError(msg(e));
    });
  }

  function requestDeactivate(): void {
    if (!isActive || busy || !active) return;
    if (!window.confirm(t("providers.confirms.deactivate", {
      provider: entry.display, model: active.model_id,
    }))) return;
    setCardError("");
    void onDeactivate(revision).catch((e: unknown) => {
      if (!isConflict(e)) setCardError(msg(e));
    });
  }

  const keyId = `prov-key-${id}`;
  const baseId = `prov-base-${id}`;
  const searchId = `prov-search-${id}`;
  const modelId = `prov-model-${id}`;

  return (
    <Panel
      icon={isActive ? "spark" : undefined}
      tint={isActive ? "var(--shell-green-soft)" : undefined}
      title={entry.display}
      sub={kindLabel(entry.kind)}
      action={(
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <Badge tone={entry.configured ? "active" : "muted"}>
            {entry.configured ? t("providers.configured") : t("providers.notConfigured")}
          </Badge>
          {isActive ? (
            <Badge tone="active">
              <span role="status">{t("providers.activeBadge")}</span>
            </Badge>
          ) : null}
        </span>
      )}
    >
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 12 }}>
        <Switch
          checked={isActive}
          disabled={busy !== null}
          label={isActive ? t("providers.activeBadge") : t("providers.useAsActive", { provider: entry.display })}
          onChange={(v) => { if (v) requestActivate(); else requestDeactivate(); }}
        />
        {busy !== null ? (
          <span className="panel-sub" role="status" style={{ fontSize: 12 }}>
            {busy === "deactivate" ? t("providers.deactivating") : t("providers.activating")}
          </span>
        ) : null}
      </div>

      {cardError ? <p role="alert" className="empty" style={{ textAlign: "left" }}>{cardError}</p> : null}

      {needsKey ? (
        <div className="field" style={{ marginBottom: 10 }}>
          <label htmlFor={keyId}>{t("providers.keyLabel", { provider: entry.display })}</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <input
              id={keyId}
              type={showKey ? "text" : "password"}
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder={entry.has_secret ? t("providers.keyMasked") : t("providers.keyPlaceholder")}
              autoComplete="off"
              spellCheck={false}
              style={{ flex: "1 1 220px", minWidth: 0 }}
            />
            <button
              type="button"
              className="btn-outline"
              aria-pressed={showKey}
              aria-label={showKey ? t("providers.hideKey") : t("providers.showKey")}
              disabled={keyInput === ""}
              onClick={() => setShowKey((s) => !s)}
            >
              <Icon name="eye" size={15} />
            </button>
            <LoadingButton
              type="button"
              className="btn-primary"
              loading={busy === `save:${id}`}
              loadingLabel={t("providers.savingKey")}
              spinnerClass="spinner"
              onClick={() => void saveKey()}
              disabled={busy !== null || keyInput.trim() === ""}
            >
              {entry.has_secret ? t("providers.replaceKey") : t("providers.saveKey")}
            </LoadingButton>
            {entry.has_secret ? (
              <LoadingButton
                type="button"
                className="btn-outline"
                loading={busy === `remove:${id}`}
                loadingLabel={t("providers.removingKey")}
                spinnerClass="spinner dark"
                onClick={() => void removeKey()}
                disabled={busy !== null}
              >
                {t("providers.removeKey")}
              </LoadingButton>
            ) : null}
          </div>
        </div>
      ) : null}

      {needsBase ? (
        <div className="field" style={{ marginBottom: 10 }}>
          <label htmlFor={baseId}>{t("providers.baseUrlLabel", { provider: entry.display })}</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <input
              id={baseId}
              type="url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={t("providers.baseUrlPlaceholder")}
              autoComplete="off"
              spellCheck={false}
              style={{ flex: "1 1 220px", minWidth: 0 }}
            />
            <LoadingButton
              type="button"
              className="btn-outline"
              loading={busy === `save-base:${id}`}
              loadingLabel={t("providers.savingKey")}
              spinnerClass="spinner dark"
              onClick={() => void saveBase()}
              disabled={busy !== null || baseUrl.trim() === "" || baseUrl === (entry.base_url ?? "")}
            >
              {t("providers.saveBaseUrl")}
            </LoadingButton>
          </div>
        </div>
      ) : null}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 10 }}>
        <span ref={testWrapRef} style={{ display: "inline-flex" }}>
        <LoadingButton
          type="button"
          className="btn-outline"
          loading={testBusy}
          loadingLabel={t("providers.testing")}
          spinnerClass="spinner dark"
          onClick={() => void runTest()}
          disabled={testBusy || busy !== null}
        >
          {t("providers.testConnection")}
        </LoadingButton>
        </span>
        {testBusy ? (
          <button type="button" className="btn-outline" onClick={cancelTest}>
            {t("providers.cancelTest")}
          </button>
        ) : null}
        {testResult ? (
          <span role="status" className="panel-sub" style={{ margin: 0 }}>
            {t("providers.testOk", { ms: testResult.ms })} {tp("providers.offeredCount", testResult.count, { count: testResult.count })}
          </span>
        ) : null}
        {testError ? <span role="alert" className="panel-sub" style={{ margin: 0 }}>{testError}</span> : null}
      </div>

      <div className="field" style={{ marginBottom: 10 }}>
        <label htmlFor={searchId}>{t("providers.modelSearchAria")}</label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <input
            ref={modelSearchRef}
            id={searchId}
            type="search"
            value={modelSearch}
            onChange={(e) => setModelSearch(e.target.value)}
            placeholder={t("providers.modelSearchPlaceholder")}
            aria-label={t("providers.modelSearchAria")}
            disabled={offered === null}
            style={{ flex: "1 1 200px", minWidth: 0 }}
          />
          <LoadingButton
            type="button"
            className="btn-outline"
            loading={busy === `refresh:${id}`}
            loadingLabel={t("providers.refreshing")}
            spinnerClass="spinner dark"
            onClick={() => void runRefresh()}
            disabled={busy !== null || testBusy}
          >
            <Icon name="reset" size={14} /> {t("providers.refreshModels")}
          </LoadingButton>
          {entry.stale ? (
            <FocusTip label={entry.fetched_at ? t("providers.cachedAt", {
              date: fmtDate(entry.fetched_at),
            }) : t("providers.staleBadge")}>
              <span style={{ display: "inline-flex" }}>
                <Badge tone="warn">{t("providers.staleBadge")}</Badge>
              </span>
            </FocusTip>
          ) : null}
        </div>
        <p className="panel-sub" style={{ margin: "6px 0" }}>
          {entry.fetched_at ? t("providers.cachedAt", { date: fmtDate(entry.fetched_at) }) : null}
          {entry.fetched_at && offered !== null ? " · " : null}
          {offered !== null ? tp("providers.offeredCount", offered.length, { count: offered.length }) : null}
        </p>
        {refreshError ? (
          <p role="alert" className="panel-sub" style={{ margin: "6px 0" }}>
            {refreshError}{" "}
            <button type="button" className="link-teal" onClick={() => void runRefresh()}>
              {t("providers.refreshRetry")}
            </button>
          </p>
        ) : null}
        <label htmlFor={modelId} style={{ marginTop: 6 }}>
          {t("providers.modelLabel", { provider: entry.display })}
        </label>
        {offered === null ? null : filtered.length === 0 ? (
          <p className="panel-sub" style={{ margin: "6px 0" }}>
            {t("providers.modelEmpty", { q: modelSearch.trim() })}
          </p>
        ) : (
          <select
            id={modelId}
            value={selectedVisible || selectedModel === "" ? selectedModel : ""}
            onChange={(e) => setSelectedModel(e.target.value)}
            style={{ maxWidth: "100%" }}
          >
            <option value="">—</option>
            {!selectedVisible && selectedModel !== "" && selectedMeta ? (
              <option value={selectedMeta.id}>
                {selectedMeta.label && selectedMeta.label !== selectedMeta.id
                  ? `${selectedMeta.label} (${selectedMeta.id})`
                  : selectedMeta.id}
              </option>
            ) : null}
            {filtered.map((m) => {
              const base = m.label && m.label !== m.id ? `${m.label} (${m.id})` : m.id;
              // Surface verified video support per exact model id;
              // unverified ids carry no suffix (never labeled capable).
              const suffix = m.support && m.support !== "unverified"
                ? ` · ${supportLabel(t, m.support)}` : "";
              return (
                <option key={m.id} value={m.id}>
                  {`${base}${suffix}`}
                </option>
              );
            })}
          </select>
        )}
        {selectedMeta ? (
          <p className="panel-sub" style={{ margin: "6px 0" }}>
            {t("providers.videoSupport", { support: supportLabel(t, selectedMeta.support) })}
            {selectedMeta.support_doc ? (
              <>
                {" "}
                <a href={selectedMeta.support_doc} target="_blank" rel="noreferrer">
                  {t("providers.videoDocs")}
                </a>
              </>
            ) : null}
          </p>
        ) : null}
      </div>
    </Panel>
  );
}
