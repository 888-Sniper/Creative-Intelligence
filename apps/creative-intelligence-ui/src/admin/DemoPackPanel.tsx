import { useCallback, useEffect, useState } from "react";

import { api } from "@/api/client";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { DemoDataBadge, EmptyState, Panel, refreshCampaignMeta } from "@/components/product";
import { SAMPLE_SCOPE_KEY } from "@/components/SampleScopeBanner";
import { useLocale } from "@/i18n";
import { EMPTY_FILTERS, useFiltersOptional } from "@/state/FilterContext";

interface PackCampaign { campaign_id: string; campaign: string; }
interface PackStatus {
  status: string;
  receipt: null | {
    batch_id: string; workspace: string; imported_by: string;
    imported_at: string; data_start: string; data_end: string;
    status: string; removed_at: string;
  };
  remaining: Record<string, number>;
  imported: Record<string, number>;
  campaigns: PackCampaign[];
}
interface PackPreview {
  status: string;
  workspace: string;
  synthetic: boolean;
  campaigns: { name: string; client: string; project: string; creatives: string[] }[];
  totals: Record<string, number | string>;
  replenish: boolean;
  migration: MigrationPreview;
}
interface MigrationPreview {
  eligible: boolean;
  reason?: string;
  v1_status?: string;
  retain?: { campaign_id: string; campaign: string }[];
  surplus?: {
    campaign_id: string; campaign: string; already_deleted: boolean;
    ads_rows: number; creatives: string[]; media_rows: number;
  }[];
  review_only?: {
    saved_views: { id: number }[]; analyst_conversations: { id: string }[];
    note: string;
  };
  v1_data_window?: { start: string; end: string };
}
interface PackFile { file_key: string; name: string; format: string; mime: string; bytes: number; }
interface PackImpact {
  campaign_id: string; campaign: string; ads_rows: number;
  creatives: number; creative_keys: string[];
  batch_views: { id: number; name: string }[];
}

function msg(fallback: string, e: unknown): string {
  if (e instanceof Error) return e.message;
  return fallback;
}

export function DemoPackPanel() {
  const { t } = useLocale();
  const statusName = (code: string): string => {
    const key = `demoPack.status.${code}`;
    const hit = t(key);
    return hit === key ? code : hit;
  };
  const [status, setStatus] = useState<PackStatus | null>(null);
  const [preview, setPreview] = useState<PackPreview | null>(null);
  const [files, setFiles] = useState<PackFile[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [impact, setImpact] = useState<PackImpact | null>(null);
  const [impactFor, setImpactFor] = useState("");
  const [renameId, setRenameId] = useState("");
  const [renameName, setRenameName] = useState("");
  const [confirmMigrate, setConfirmMigrate] = useState(false);

  const refresh = useCallback(async () => {
    const s = await api<PackStatus>("GET", "/api/admin/demo/pack/status");
    setStatus(s);
    if (s.status === "not_added" || s.status === "failed") {
      setPreview(await api<PackPreview>("GET", "/api/admin/demo/pack/preview"));
    } else {
      setPreview(null);
    }
    if (s.receipt) {
      const f = await api<{ files: PackFile[] }>("GET", "/api/admin/demo/pack/files");
      setFiles(f.files);
    } else {
      setFiles(null);
    }
  }, []);

  const reload = useCallback(() => {
    setLoadError("");
    void refresh().then(
      () => undefined,
      (e: unknown) => setLoadError(msg(t("demoPack.requestFailed"), e)),
    );
  }, [refresh]);

  useEffect(() => { reload(); }, [reload]);

  async function run(key: string, fn: () => Promise<void>): Promise<void> {
    if (busy) return;
    setBusy(key);
    setNotice("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setNotice(msg(t("demoPack.requestFailed"), e));
    } finally {
      setBusy((cur) => (cur === key ? null : cur));
    }
  }

  const importOnce = () => run("import", async () => {
    const r = await api<{ created: boolean; migration_required?: boolean }>(
      "POST", "/api/admin/demo/pack/import", {});
    if (r.migration_required) {
      setNotice(t("demoPack.migrationActive"));
    } else {
      setNotice(r.created ? t("demoPack.addedMsg") : t("demoPack.alreadyImported"));
      // Campaign lists, charts and selectors everywhere reload: normal
      // navigation afterwards shows the new campaigns with no hard reload.
      refreshCampaignMeta();
    }
    setConfirmRemove(false);
  });

  const migrate = () => run("migrate", async () => {
    const r = await api<{ authorized: boolean; deleted?: string[]; kept_deleted?: string[]; verified?: boolean }>(
      "POST", "/api/admin/demo/pack/migration/apply", { authorize: true });
    if (r.authorized) {
      const base = t("demoPack.migrationDone", {
        removed: (r.deleted ?? []).length, kept: (r.kept_deleted ?? []).length,
      });
      setNotice(r.verified === false
        ? `${base} ${t("demoPack.verifyFailed")}`
        : `${base} ${t("demoPack.verifyPassed")}`);
      refreshCampaignMeta();
    }
    setConfirmMigrate(false);
  });

  const filtersCtx = useFiltersOptional();
  const openDemoDashboard = () => {
    if (!status?.receipt) return;
    try {
      // Snapshot the live pre-demo filters before navigating away: a full
      // page load resets FilterContext, so the banner can only restore
      // what we store here. Preserve an existing in-progress scope's
      // saved filters when one is active (re-open must not clobber it).
      let prev: unknown;
      let applied: unknown;
      let scopeActive = false;
      try {
        const cur = JSON.parse(
          localStorage.getItem(SAMPLE_SCOPE_KEY) ?? "null") as {
            prev?: unknown; applied?: unknown } | null;
        scopeActive = cur?.applied === true;
        if (scopeActive) prev = cur?.prev;
        applied = cur?.applied;
      } catch { /* corrupt scope: start fresh */ }
      const live = filtersCtx?.filters;
      // Live snapshot only when no demo session is active: mid-demo
      // drill-down filters must never overwrite the original return path.
      if (live && !scopeActive) {
        const snap: Record<string, string> = {};
        (Object.keys(EMPTY_FILTERS) as (keyof typeof EMPTY_FILTERS)[]).forEach((k) => {
          if (live[k] !== EMPTY_FILTERS[k]) snap[k] = live[k];
        });
        if (Object.keys(snap).length > 0) prev = snap;
      }
      localStorage.setItem(SAMPLE_SCOPE_KEY, JSON.stringify({
        from: status.receipt.data_start,
        to: status.receipt.data_end,
        batch: status.receipt.batch_id,
        ...(prev !== undefined ? { prev } : {}),
        ...(applied !== undefined ? { applied } : {}),
      }));
    } catch { /* storage unavailable: still navigate */ }
    window.location.assign("/");
  };

  const removeAll = () => run("remove", async () => {
    if (!status?.receipt) return;
    await api("POST", "/api/admin/demo/pack/remove",
      { confirm: true, batch_id: status.receipt.batch_id });
    setNotice(t("demoPack.removedMsg"));
    refreshCampaignMeta();
    setConfirmRemove(false);
    setImpact(null);
  });

  const askImpact = (campaignId: string) => run(`impact:${campaignId}`, async () => {
    const r = await api<PackImpact>(
      "GET", `/api/admin/demo/pack/impact?campaign_id=${encodeURIComponent(campaignId)}`);
    setImpact(r);
    setImpactFor(campaignId);
  });

  const deleteCampaign = (campaignId: string) => run(`del:${campaignId}`, async () => {
    await api("DELETE", `/api/admin/demo/pack/campaigns/${encodeURIComponent(campaignId)}`);
    setNotice(t("demoPack.deletedCamp"));
    setImpact(null);
  });

  const renameCampaign = () => run("rename", async () => {
    if (!renameId || !renameName.trim()) return;
    await api("POST", "/api/admin/demo/pack/rename",
      { kind: "campaign", id: renameId, name: renameName.trim() });
    setNotice(t("demoPack.renamedMsg"));
    refreshCampaignMeta();
    setRenameId("");
    setRenameName("");
  });

  const deleteFile = (fileKey: string) => run(`file:${fileKey}`, async () => {
    await api("DELETE", `/api/admin/demo/pack/files/${encodeURIComponent(fileKey)}`);
    setNotice(t("demoPack.deletedFile"));
  });

  if (loadError && !status) {
    return (
      <Panel title={t("demoPack.title")}>
        <EmptyState icon="compare" title={t("demoPack.loadFailedTitle")}
          text={t("demoPack.loadFailedBody", { error: loadError })}
          action={<button type="button" className="btn-outline" onClick={reload}>{t("demoPack.retry")}</button>} />
      </Panel>
    );
  }
  if (!status) {
    return (
      <Panel title={t("demoPack.title")}>
        <EmptyState icon="clock" title={t("demoPack.loadingTitle")} text={t("demoPack.loadingBody")} />
      </Panel>
    );
  }

  const receipt = status.receipt;
  const imported = status.imported ?? {};
  const remaining = status.remaining ?? {};
  const migration = preview?.migration;

  return (
    <Panel
      title={t("demoPack.title")}
      sub={t("demoPack.sub")}
      action={<DemoDataBadge />}
    >
      {notice ? <p className="panel-sub" role="status" style={{ margin: "0 0 8px" }}>{notice}</p> : null}
      {loadError ? <p className="panel-sub" role="alert" style={{ margin: "0 0 8px" }}>{t("demoPack.loadFailedBody", { error: loadError })}</p> : null}

      {receipt ? (
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
          <span className="badge-demo">{t("demoPack.sampleBadge")}</span>
          <span className="panel-sub" style={{ margin: 0 }}>
            {t("demoPack.importedLine", {
              at: receipt.imported_at || t("demoPack.unknownDate"),
              by: receipt.imported_by || t("demoPack.unknownDate"),
              from: receipt.data_start || t("demoPack.unknownDate"),
              to: receipt.data_end || t("demoPack.unknownDate"),
              status: statusName(status.status),
            })}
          </span>
        </div>
      ) : null}

      {(status.status === "added" || status.status === "partially_removed") && receipt ? (
        <p className="panel-sub" style={{ margin: "0 0 8px" }}>
          {t("demoPack.remainingLine", {
            camps: `${remaining.campaigns ?? 0}/${imported.campaigns ?? 5}`,
            creatives: `${remaining.creatives ?? 0}/${imported.creatives ?? 15}`,
            rows: remaining.ads_rows ?? 0,
          })}{" "}
          <button type="button" className="link-btn" onClick={openDemoDashboard}>
            {t("demoPack.openDemo")}
          </button>
          {receipt ? ` ${t("demoPack.suggestedRange", { from: receipt.data_start, to: receipt.data_end })}` : ""}
        </p>
      ) : null}

      {status.status === "not_added" || status.status === "failed" ? (
        <>
          {status.status === "failed" ? (
            <p className="panel-sub" role="alert" style={{ margin: "0 0 8px" }}>
              {t("demoPack.importFailedNote")}
            </p>
          ) : null}
          {preview ? (
            <div style={{ marginBottom: 8 }}>
              <p className="panel-sub" style={{ margin: "0 0 4px" }}>
                {t("demoPack.targetLine", {
                  workspace: preview.workspace,
                  synthetic: preview.synthetic ? t("demoPack.yes") : t("demoPack.no"),
                  replenish: preview.replenish ? t("demoPack.yes") : t("demoPack.noReplenish"),
                })}
              </p>
              <p className="panel-sub" style={{ margin: "0 0 4px" }}>
                {t("demoPack.willCreate", {
                  days: preview.totals.days, views: preview.totals.saved_views,
                  convs: preview.totals.conversations, reports: preview.totals.reports,
                  books: preview.totals.workbooks,
                })}
              </p>
            </div>
          ) : null}
          {migration?.eligible ? (
            <div style={{ marginBottom: 8 }}>
              <p className="panel-sub" style={{ margin: "0 0 4px" }}>
                {t("demoPack.migrationNote", { status: migration.v1_status ?? "" })}
              </p>
              <ul className="plain" style={{ margin: "0 0 4px", padding: 0, listStyle: "none" }}>
                {(migration.surplus ?? []).map((s) => (
                  <li key={s.campaign_id} className="panel-sub" style={{ margin: 0 }}>
                    {s.already_deleted
                      ? t("demoPack.surplusDeleted", { id: s.campaign_id })
                      : t("demoPack.surplusRemove", {
                          name: s.campaign || s.campaign_id, rows: s.ads_rows,
                          creatives: s.creatives.length, media: s.media_rows,
                        })}
                  </li>
                ))}
              </ul>
              <p className="panel-sub" style={{ margin: "0 0 4px" }}>
                {t("demoPack.reviewOnlyNote", {
                  views: migration.review_only?.saved_views.length ?? 0,
                  convs: migration.review_only?.analyst_conversations.length ?? 0,
                })}
              </p>
              {!confirmMigrate ? (
                <button type="button" className="btn-outline" disabled={busy !== null}
                  onClick={() => setConfirmMigrate(true)}>
                  {t("demoPack.reviewMigration")}
                </button>
              ) : (
                <>
                  <span className="panel-sub" style={{ margin: 0 }}>
                    {t("demoPack.applyMigration")}
                  </span>{" "}
                  <LoadingButton type="button" className="btn-outline" loading={busy === "migrate"}
                    loadingLabel={t("demoPack.migrating")} spinnerClass="spinner dark" disabled={busy !== null}
                    onClick={() => void migrate()}>
                    {t("demoPack.confirmMigration")}
                  </LoadingButton>{" "}
                  <button type="button" className="btn-outline" disabled={busy !== null}
                    onClick={() => setConfirmMigrate(false)}>
                    {t("demoPack.cancel")}
                  </button>
                </>
              )}
            </div>
          ) : null}
          <LoadingButton type="button" className="btn-outline" loading={busy === "import"}
            loadingLabel={t("demoPack.addBusy")} spinnerClass="spinner dark" disabled={busy !== null}
            onClick={() => void importOnce()}>
            <Icon name="download" size={15} /> {t("demoPack.addOnce")}
          </LoadingButton>
        </>
      ) : null}

      {(status.status === "added" || status.status === "partially_removed") && receipt ? (
        <>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
            {!confirmRemove ? (
              <LoadingButton type="button" className="btn-outline" loading={false}
                loadingLabel={t("demoPack.removeBusy")} spinnerClass="spinner dark" disabled={busy !== null}
                onClick={() => setConfirmRemove(true)}>
                <Icon name="x" size={15} /> {t("demoPack.removeAll")}
              </LoadingButton>
            ) : (
              <>
                <span className="panel-sub" style={{ margin: 0 }}>
                  {t("demoPack.removeConfirm", {
                    camps: remaining.campaigns ?? 0, creatives: remaining.creatives ?? 0,
                    rows: remaining.ads_rows ?? 0, files: remaining.sample_files ?? 0,
                  })}
                </span>
                <LoadingButton type="button" className="btn-outline" loading={busy === "remove"}
                  loadingLabel={t("demoPack.removeBusy")} spinnerClass="spinner dark" disabled={busy !== null}
                  onClick={() => void removeAll()}>
                  {t("demoPack.confirmRemoval")}
                </LoadingButton>
                <button type="button" className="btn-outline" disabled={busy !== null}
                  onClick={() => setConfirmRemove(false)}>
                  {t("demoPack.cancel")}
                </button>
              </>
            )}
          </div>

          {status.campaigns.length > 0 ? (
            <div style={{ marginTop: 10 }}>
              <h4 style={{ margin: "0 0 6px", fontSize: 13 }}>{t("demoPack.sampleCamps")}</h4>
              <ul className="plain" style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {status.campaigns.map((c) => (
                  <li key={c.campaign_id}
                    style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", padding: "4px 0" }}>
                    <span style={{ minWidth: 220 }}>{c.campaign}</span>
                    <span className="panel-sub" style={{ margin: 0 }}>{c.campaign_id}</span>
                    <button type="button" className="link-btn" disabled={busy !== null}
                      onClick={() => void askImpact(c.campaign_id)}>
                      {t("demoPack.deleteDot")}
                    </button>
                    {impact && impactFor === c.campaign_id ? (
                      <span className="panel-sub" style={{ margin: 0 }}>
                        {t("demoPack.impactLine", {
                          name: impact.campaign, rows: impact.ads_rows,
                          creatives: impact.creatives,
                          views: impact.batch_views.length > 0
                            ? t("demoPack.impactViews", { count: impact.batch_views.length }) : "",
                        })}{" "}
                        <button type="button" className="link-btn" disabled={busy !== null}
                          onClick={() => void deleteCampaign(c.campaign_id)}>
                          {t("demoPack.confirmDelete")}
                        </button>{" "}
                        <button type="button" className="link-btn" disabled={busy !== null}
                          onClick={() => setImpact(null)}>
                          {t("demoPack.cancel")}
                        </button>
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
                <select aria-label={t("demoPack.renameAria")} value={renameId}
                  onChange={(e) => setRenameId(e.target.value)} disabled={busy !== null}>
                  <option value="">{t("demoPack.renameOption")}</option>
                  {status.campaigns.map((c) => (
                    <option key={c.campaign_id} value={c.campaign_id}>{c.campaign}</option>
                  ))}
                </select>
                <input aria-label={t("demoPack.newNameAria")} placeholder={t("demoPack.newNamePh")} value={renameName}
                  onChange={(e) => setRenameName(e.target.value)} disabled={busy !== null}
                  style={{ width: 180 }} />
                <LoadingButton type="button" className="btn-outline" loading={busy === "rename"}
                  loadingLabel={t("demoPack.renaming")} spinnerClass="spinner dark"
                  disabled={busy !== null || !renameId || !renameName.trim()}
                  onClick={() => void renameCampaign()}>
                  {t("demoPack.renameBtn")}
                </LoadingButton>
              </div>
            </div>
          ) : null}

          {files && files.length > 0 ? (
            <div style={{ marginTop: 10 }}>
              <h4 style={{ margin: "0 0 6px", fontSize: 13 }}>{t("demoPack.sampleFiles")}</h4>
              <ul className="plain" style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {files.map((f) => (
                  <li key={f.file_key} style={{ display: "flex", gap: 8, alignItems: "center", padding: "4px 0" }}>
                    <a className="link-teal" href={`/api/admin/demo/pack/files/${encodeURIComponent(f.file_key)}`}>
                      {f.name}
                    </a>
                    <span className="panel-sub" style={{ margin: 0 }}>{f.format} · {f.bytes} B</span>
                    <button type="button" className="link-btn" disabled={busy !== null}
                      onClick={() => void deleteFile(f.file_key)}>
                      {t("demoPack.deleteFileBtn")}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}

      {status.status === "removed" ? (
        <EmptyState verbatim text={t("demoPack.removedEmpty")} />
      ) : null}
    </Panel>
  );
}
