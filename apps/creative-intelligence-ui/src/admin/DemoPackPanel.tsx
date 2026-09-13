import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { DemoDataBadge, EmptyState, Panel, Skeleton } from "@/components/product";

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
  legacy_demo: { campaigns: number; creatives: number };
  replenish: boolean;
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
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [impact, setImpact] = useState<PackImpact | null>(null);
  const [impactFor, setImpactFor] = useState("");
  const [renameId, setRenameId] = useState("");
  const [renameName, setRenameName] = useState("");

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

  useEffect(() => { void refresh().catch((e: unknown) => setNotice(msg(e))); }, [refresh]);

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
    const r = await api<{ created: boolean }>("POST", "/api/admin/demo/pack/import", {});
    setNotice(r.created ? "Sample Data Added." : "Pack Already Imported — Nothing Duplicated.");
    setConfirmRemove(false);
  });

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

  if (!status) return <Skeleton height={120} />;

  const receipt = status.receipt;
  const imported = status.imported ?? {};
  const remaining = status.remaining ?? {};

  return (
    <Panel
      title="Demo Data"
      sub="One-time presentation pack (foap-presentation-pack-v1). Synthetic demonstration figures — never real client performance. Deleted samples stay deleted."
      action={<DemoDataBadge />}
    >
      {notice ? <p className="panel-sub" role="status" style={{ margin: "0 0 8px" }}>{notice}</p> : null}

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
          Remaining: {remaining.campaigns ?? 0}/{imported.campaigns ?? 10} Campaign(s),{" "}
          {remaining.creatives ?? 0}/{imported.creatives ?? 30} Creative(s),{" "}
          {remaining.ads_rows ?? 0} Performance Row(s).{" "}
          <Link className="link-teal" to="/">Open Demo Dashboard</Link>
          {receipt ? ` (Suggested Range: ${receipt.data_start} → ${receipt.data_end}.)` : ""}
        </p>
      ) : null}

      {status.status === "not_added" || status.status === "failed" ? (
        <>
          {preview ? (
            <div style={{ marginBottom: 8 }}>
              <p className="panel-sub" style={{ margin: "0 0 4px" }}>
                Target: {preview.workspace} · Synthetic: {preview.synthetic ? "Yes" : "No"} ·
                Replenishes Itself: {preview.replenish ? "Yes" : "No — Deleted Samples Stay Deleted."}
              </p>
              <p className="panel-sub" style={{ margin: "0 0 4px" }}>
                Will Create: 10 Campaign(s), 30 Creative(s), {preview.totals.days} Day(s) Of
                Performance Rows, {preview.totals.saved_views} Saved View(s),{" "}
                {preview.totals.conversations} Conversation(s), {preview.totals.reports} Report(s),{" "}
                {preview.totals.workbooks} Workbook(s).
              </p>
              {preview.legacy_demo.campaigns > 0 || preview.legacy_demo.creatives > 0 ? (
                <p className="panel-sub" style={{ margin: "0 0 4px" }}>
                  Older Sample Records Present: {preview.legacy_demo.campaigns} Campaign(s),{" "}
                  {preview.legacy_demo.creatives} Creative(s). They Are Left Untouched.
                </p>
              ) : null}
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
        <EmptyState text="Sample Data Removed. The Import Receipt Is Kept — This Pack Will Not Be Offered Again." />
      ) : null}
    </Panel>
  );
}
