import { useCallback, useEffect, useState } from "react";

import { api } from "@/api/client";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { DemoDataBadge, EmptyState, Panel } from "@/components/product";
import { SAMPLE_SCOPE_KEY } from "@/components/SampleScopeBanner";

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

function msg(e: unknown): string {
  if (e instanceof Error) return e.message;
  return "Request Failed.";
}

export function DemoPackPanel() {
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
      (e: unknown) => setLoadError(msg(e)),
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
      setNotice(msg(e));
    } finally {
      setBusy((cur) => (cur === key ? null : cur));
    }
  }

  const importOnce = () => run("import", async () => {
    const r = await api<{ created: boolean; migration_required?: boolean }>(
      "POST", "/api/admin/demo/pack/import", {});
    if (r.migration_required) {
      setNotice("An Earlier Sample Pack Is Active — Review The Migration Preview Below Before Adding.");
    } else {
      setNotice(r.created ? "Sample Data Added." : "Pack Already Imported — Nothing Duplicated.");
    }
    setConfirmRemove(false);
  });

  const migrate = () => run("migrate", async () => {
    const r = await api<{ authorized: boolean; deleted?: string[]; kept_deleted?: string[] }>(
      "POST", "/api/admin/demo/pack/migration/apply", { authorize: true });
    if (r.authorized) {
      setNotice(`Migration Complete. Removed ${(r.deleted ?? []).length} Surplus Campaign(s); ` +
        `Kept ${(r.kept_deleted ?? []).length} Earlier Deletion(s).`);
    }
    setConfirmMigrate(false);
  });

  const openDemoDashboard = () => {
    if (!status?.receipt) return;
    try {
      localStorage.setItem(SAMPLE_SCOPE_KEY, JSON.stringify({
        from: status.receipt.data_start,
        to: status.receipt.data_end,
        batch: status.receipt.batch_id,
      }));
    } catch { /* storage unavailable: still navigate */ }
    window.location.assign("/");
  };

  const removeAll = () => run("remove", async () => {
    if (!status?.receipt) return;
    await api("POST", "/api/admin/demo/pack/remove",
      { confirm: true, batch_id: status.receipt.batch_id });
    setNotice("Sample Data Removed. The Import Receipt Is Kept.");
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
    setNotice("Sample Campaign Deleted. It Will Not Return.");
    setImpact(null);
  });

  const renameCampaign = () => run("rename", async () => {
    if (!renameId || !renameName.trim()) return;
    await api("POST", "/api/admin/demo/pack/rename",
      { kind: "campaign", id: renameId, name: renameName.trim() });
    setNotice("Sample Campaign Renamed. Cleanup Provenance Kept.");
    setRenameId("");
    setRenameName("");
  });

  const deleteFile = (fileKey: string) => run(`file:${fileKey}`, async () => {
    await api("DELETE", `/api/admin/demo/pack/files/${encodeURIComponent(fileKey)}`);
    setNotice("Sample File Deleted.");
  });

  if (loadError && !status) {
    return (
      <Panel title="Demo Data">
        <EmptyState icon="compare" title="Could Not Load Sample Status"
          text={`Sample pack status unavailable: ${loadError}`}
          action={<button type="button" className="btn-outline" onClick={reload}>Retry</button>} />
      </Panel>
    );
  }
  if (!status) {
    return (
      <Panel title="Demo Data">
        <EmptyState icon="clock" title="Loading Sample Status" text="Fetching the import receipt…" />
      </Panel>
    );
  }

  const receipt = status.receipt;
  const imported = status.imported ?? {};
  const remaining = status.remaining ?? {};
  const migration = preview?.migration;

  return (
    <Panel
      title="Demo Data"
      sub="One-time presentation pack (foap-presentation-pack-v2): 5 campaigns × 3 creatives. Synthetic demonstration figures — never real client performance. Deleted samples stay deleted."
      action={<DemoDataBadge />}
    >
      {notice ? <p className="panel-sub" role="status" style={{ margin: "0 0 8px" }}>{notice}</p> : null}
      {loadError ? <p className="panel-sub" role="alert" style={{ margin: "0 0 8px" }}>Sample pack status unavailable: {loadError}</p> : null}

      {receipt ? (
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
          <span className="badge-demo">Sample Data</span>
          <span className="panel-sub" style={{ margin: 0 }}>
            Imported {receipt.imported_at || "—"} by {receipt.imported_by || "—"} ·
            Data {receipt.data_start || "—"} → {receipt.data_end || "—"} ·
            Status: {status.status}
          </span>
        </div>
      ) : null}

      {(status.status === "added" || status.status === "partially_removed") && receipt ? (
        <p className="panel-sub" style={{ margin: "0 0 8px" }}>
          Remaining: {remaining.campaigns ?? 0}/{imported.campaigns ?? 5} Campaign(s),{" "}
          {remaining.creatives ?? 0}/{imported.creatives ?? 15} Creative(s),{" "}
          {remaining.ads_rows ?? 0} Performance Row(s).{" "}
          <button type="button" className="link-btn" onClick={openDemoDashboard}>
            Open Demo Dashboard
          </button>
          {receipt ? ` (Suggested Range: ${receipt.data_start} → ${receipt.data_end}.)` : ""}
        </p>
      ) : null}

      {status.status === "not_added" || status.status === "failed" ? (
        <>
          {status.status === "failed" ? (
            <p className="panel-sub" role="alert" style={{ margin: "0 0 8px" }}>
              The Last Import Did Not Finish. Nothing Was Left Half-Visible: Fix The Cause,
              Then Retry — Completed Work Is Kept And Missing Work Resumes.
            </p>
          ) : null}
          {preview ? (
            <div style={{ marginBottom: 8 }}>
              <p className="panel-sub" style={{ margin: "0 0 4px" }}>
                Target: {preview.workspace} · Synthetic: {preview.synthetic ? "Yes" : "No"} ·
                Replenishes Itself: {preview.replenish ? "Yes" : "No — Deleted Samples Stay Deleted."}
              </p>
              <p className="panel-sub" style={{ margin: "0 0 4px" }}>
                Will Create: 5 Campaign(s), 15 Creative(s), {preview.totals.days} Day(s) Of
                Performance Rows, {preview.totals.saved_views} Saved View(s),{" "}
                {preview.totals.conversations} Conversation(s), {preview.totals.reports} Report(s),{" "}
                {preview.totals.workbooks} Workbook(s).
              </p>
            </div>
          ) : null}
          {migration?.eligible ? (
            <div style={{ marginBottom: 8 }}>
              <p className="panel-sub" style={{ margin: "0 0 4px" }}>
                An Earlier 10-Campaign Pack Is Active ({migration.v1_status}). A Fresh Import
                Will Not Install Beside It. Migration Keeps The Five Matching Campaigns And
                Removes Only Sample-Owned Surplus Records.
              </p>
              <ul className="plain" style={{ margin: "0 0 4px", padding: 0, listStyle: "none" }}>
                {(migration.surplus ?? []).map((s) => (
                  <li key={s.campaign_id} className="panel-sub" style={{ margin: 0 }}>
                    {s.already_deleted
                      ? `Already Deleted By You (Stays Deleted): ${s.campaign_id}`
                      : `Remove: ${s.campaign || s.campaign_id} — ${s.ads_rows} Row(s), ` +
                        `${s.creatives.length} Creative(s), ${s.media_rows} Media File(s)`}
                  </li>
                ))}
              </ul>
              <p className="panel-sub" style={{ margin: "0 0 4px" }}>
                Saved Views ({migration.review_only?.saved_views.length ?? 0}) And Conversations
                ({migration.review_only?.analyst_conversations.length ?? 0}) Are Never Auto-Deleted.
              </p>
              {!confirmMigrate ? (
                <button type="button" className="btn-outline" disabled={busy !== null}
                  onClick={() => setConfirmMigrate(true)}>
                  Review Migration…
                </button>
              ) : (
                <>
                  <span className="panel-sub" style={{ margin: 0 }}>
                    Apply The Migration Described Above? Your Earlier Deletions Stay Deleted.
                  </span>{" "}
                  <LoadingButton type="button" className="btn-outline" loading={busy === "migrate"}
                    loadingLabel="Migrating…" spinnerClass="spinner dark" disabled={busy !== null}
                    onClick={() => void migrate()}>
                    Confirm Migration
                  </LoadingButton>{" "}
                  <button type="button" className="btn-outline" disabled={busy !== null}
                    onClick={() => setConfirmMigrate(false)}>
                    Cancel
                  </button>
                </>
              )}
            </div>
          ) : null}
          <LoadingButton type="button" className="btn-outline" loading={busy === "import"}
            loadingLabel="Adding Demo Data…" spinnerClass="spinner dark" disabled={busy !== null}
            onClick={() => void importOnce()}>
            <Icon name="download" size={15} /> Add Demo Data Once
          </LoadingButton>
        </>
      ) : null}

      {(status.status === "added" || status.status === "partially_removed") && receipt ? (
        <>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
            {!confirmRemove ? (
              <LoadingButton type="button" className="btn-outline" loading={false}
                loadingLabel="Removing Demo Data…" spinnerClass="spinner dark" disabled={busy !== null}
                onClick={() => setConfirmRemove(true)}>
                <Icon name="x" size={15} /> Remove All Demo Data
              </LoadingButton>
            ) : (
              <>
                <span className="panel-sub" style={{ margin: 0 }}>
                  This removes the remaining {remaining.campaigns ?? 0} campaign(s),{" "}
                  {remaining.creatives ?? 0} creative(s), {remaining.ads_rows ?? 0} performance row(s)
                  and {remaining.sample_files ?? 0} file(s) from this pack only.
                  Employee accounts, connected accounts and real imported data will not be removed.
                </span>
                <LoadingButton type="button" className="btn-outline" loading={busy === "remove"}
                  loadingLabel="Removing Demo Data…" spinnerClass="spinner dark" disabled={busy !== null}
                  onClick={() => void removeAll()}>
                  Confirm Removal
                </LoadingButton>
                <button type="button" className="btn-outline" disabled={busy !== null}
                  onClick={() => setConfirmRemove(false)}>
                  Cancel
                </button>
              </>
            )}
          </div>

          {status.campaigns.length > 0 ? (
            <div style={{ marginTop: 10 }}>
              <h4 style={{ margin: "0 0 6px", fontSize: 13 }}>Sample Campaigns</h4>
              <ul className="plain" style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {status.campaigns.map((c) => (
                  <li key={c.campaign_id}
                    style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", padding: "4px 0" }}>
                    <span style={{ minWidth: 220 }}>{c.campaign}</span>
                    <span className="panel-sub" style={{ margin: 0 }}>{c.campaign_id}</span>
                    <button type="button" className="link-btn" disabled={busy !== null}
                      onClick={() => void askImpact(c.campaign_id)}>
                      Delete…
                    </button>
                    {impact && impactFor === c.campaign_id ? (
                      <span className="panel-sub" style={{ margin: 0 }}>
                        Removes “{impact.campaign}”: {impact.ads_rows} row(s),{" "}
                        {impact.creatives} creative(s)
                        {impact.batch_views.length > 0
                          ? `, ${impact.batch_views.length} saved view(s)` : ""}.{" "}
                        <button type="button" className="link-btn" disabled={busy !== null}
                          onClick={() => void deleteCampaign(c.campaign_id)}>
                          Confirm Delete
                        </button>{" "}
                        <button type="button" className="link-btn" disabled={busy !== null}
                          onClick={() => setImpact(null)}>
                          Cancel
                        </button>
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
                <select aria-label="Sample Campaign To Rename" value={renameId}
                  onChange={(e) => setRenameId(e.target.value)} disabled={busy !== null}>
                  <option value="">Rename Campaign…</option>
                  {status.campaigns.map((c) => (
                    <option key={c.campaign_id} value={c.campaign_id}>{c.campaign}</option>
                  ))}
                </select>
                <input aria-label="New Campaign Name" placeholder="New Name" value={renameName}
                  onChange={(e) => setRenameName(e.target.value)} disabled={busy !== null}
                  style={{ width: 180 }} />
                <LoadingButton type="button" className="btn-outline" loading={busy === "rename"}
                  loadingLabel="Renaming…" spinnerClass="spinner dark"
                  disabled={busy !== null || !renameId || !renameName.trim()}
                  onClick={() => void renameCampaign()}>
                  Rename
                </LoadingButton>
              </div>
            </div>
          ) : null}

          {files && files.length > 0 ? (
            <div style={{ marginTop: 10 }}>
              <h4 style={{ margin: "0 0 6px", fontSize: 13 }}>Sample Files</h4>
              <ul className="plain" style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {files.map((f) => (
                  <li key={f.file_key} style={{ display: "flex", gap: 8, alignItems: "center", padding: "4px 0" }}>
                    <a className="link-teal" href={`/api/admin/demo/pack/files/${encodeURIComponent(f.file_key)}`}>
                      {f.name}
                    </a>
                    <span className="panel-sub" style={{ margin: 0 }}>{f.format} · {f.bytes} B</span>
                    <button type="button" className="link-btn" disabled={busy !== null}
                      onClick={() => void deleteFile(f.file_key)}>
                      Delete
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}

      {status.status === "removed" ? (
        <EmptyState text="Sample Data Removed. The Import Receipt Is Kept — This Pack Will Not Return On Its Own." />
      ) : null}
    </Panel>
  );
}
