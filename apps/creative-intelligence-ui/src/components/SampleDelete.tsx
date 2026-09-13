import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { LoadingButton } from "@/components/LoadingButton";
import { refreshCampaignMeta } from "@/components/product";

/** Null outside AuthProvider (tests, signed-out trees): the control
 *  is admin-gated anyway, so no provider means no button. */
function useAdminFlag(): boolean {
  try {
    return useAuth().me?.is_admin === true;
  } catch {
    return false;
  }
}

interface PackStatusLite {
  status: string;
  receipt: { batch_id: string } | null;
  campaigns: { campaign_id: string; campaign: string }[];
}

let packPromise: Promise<PackStatusLite> | null = null;
function fetchPack(): Promise<PackStatusLite> {
  if (!packPromise) {
    packPromise = api<PackStatusLite>("GET", "/api/admin/demo/pack/status")
      .catch((e: unknown) => {
        packPromise = null;
        throw e;
      });
  }
  return packPromise;
}
export function refreshPackStatus(): void {
  packPromise = null;
}

/** Admin-gated sample-campaign delete with impact preview, confirm and
 *  post-delete refresh (page lists + shared metadata). Renders nothing
 *  for non-admins or non-sample campaigns. */
export function SampleCampaignDelete({ campaignName, onDeleted }: {
  campaignName: string; onDeleted: () => void;
}) {
  const isAdmin = useAdminFlag();
  const [pack, setPack] = useState<PackStatusLite | null>(null);
  const [showImpact, setShowImpact] = useState(false);
  const [impact, setImpact] = useState<{
    campaign: string; ads_rows: number; creatives: number;
    batch_views: { id: number; name: string }[];
  } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isAdmin) return;
    let live = true;
    fetchPack().then((p) => live && setPack(p)).catch(() => undefined);
    return () => { live = false; };
  }, [isAdmin]);

  if (!isAdmin || !pack?.receipt) return null;
  const match = pack.campaigns.find((c) => c.campaign === campaignName);
  if (!match) return null;

  const ask = async () => {
    if (busy) return;
    setBusy("impact");
    setError("");
    try {
      const r = await api<typeof impact>(
        "GET", `/api/admin/demo/pack/impact?campaign_id=${encodeURIComponent(match.campaign_id)}`);
      setImpact(r);
      setShowImpact(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request Failed.");
    } finally {
      setBusy(null);
    }
  };

  const del = async () => {
    if (busy) return;
    setBusy("del");
    setError("");
    try {
      await api("DELETE",
        `/api/admin/demo/pack/campaigns/${encodeURIComponent(match.campaign_id)}`);
      refreshPackStatus();
      refreshCampaignMeta();
      setShowImpact(false);
      setImpact(null);
      onDeleted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request Failed.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
      {!showImpact ? (
        <button type="button" className="link-btn" disabled={busy !== null} onClick={() => void ask()}>
          Delete Sample…
        </button>
      ) : (
        <span className="panel-sub" style={{ margin: 0 }}>
          Removes “{impact?.campaign}”: {impact?.ads_rows} row(s), {impact?.creatives} creative(s)
          {(impact?.batch_views.length ?? 0) > 0 ? `, ${impact?.batch_views.length} saved view(s)` : ""}.{" "}
          <LoadingButton type="button" className="link-btn" loading={busy === "del"}
            loadingLabel="Deleting…" disabled={busy !== null} onClick={() => void del()}>
            Confirm Delete
          </LoadingButton>{" "}
          <button type="button" className="link-btn" disabled={busy !== null}
            onClick={() => { setShowImpact(false); setImpact(null); }}>
            Cancel
          </button>
        </span>
      )}
      {error ? <span className="panel-sub" role="alert" style={{ margin: 0 }}>{error}</span> : null}
    </span>
  );
}
