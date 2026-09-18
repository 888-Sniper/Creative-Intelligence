import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/auth/AuthProvider";
import { useLocale } from "@/i18n";
import { Icon } from "@/components/icons";
import { CreativeThumb, EmptyState, Skeleton, Toast } from "@/components/product";
import {
  isVideoFile,
  VideoUploadPanel,
  type PanelOpen,
} from "@/components/VideoUploadPanel";
import {
  cancelAnalysisJob,
  deleteDraft,
  draftKey,
  getDraft,
  listDrafts,
  patchDraft,
  type DraftView,
} from "@/components/videoUploadApi";

const TERMINAL_VIEW = ["queued", "analyzing", "ready_for_review", "reviewed"];
const RETRYABLE = ["failed", "cancelled", "expired"];

function draftName(d: DraftView): string {
  return (
    d.spec?.media?.filename ||
    d.spec?.creative_key ||
    d.videos?.[0]?.creative_key ||
    d.id.slice(0, 8)
  );
}

function draftSeed(d: DraftView): string {
  return d.spec?.creative_key || d.videos?.[0]?.creative_key || d.id;
}

export function VideoUploadCard() {
  const { me } = useAuth();
  const { t, fmtDate } = useLocale();
  const vu = (key: string, vars?: Record<string, string | number>): string =>
    t(`dashboard.videoUpload.${key}`, vars);
  const employeeId = me?.employee?.id ?? "";
  const [panel, setPanel] = useState<PanelOpen | null>(null);
  const [drafts, setDrafts] = useState<DraftView[] | null>(null);
  const [draftsError, setDraftsError] = useState("");
  const [resume, setResume] = useState<DraftView | null>(null);
  const [toast, setToast] = useState("");
  const [cardMsg, setCardMsg] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [busyDelete, setBusyDelete] = useState(false);
  const [busyCancel, setBusyCancel] = useState(false);

  const statusName = (status: string): string => {
    const key = `dashboard.videoUpload.statusNames.${status}`;
    const hit = t(key);
    return hit === key ? status : hit;
  };

  const reload = async (): Promise<void> => {
    try {
      setDrafts(await listDrafts());
      setDraftsError("");
    } catch (e) {
      setDraftsError(e instanceof Error ? e.message : String(e));
    }
    try {
      const pinned = window.localStorage.getItem(draftKey(employeeId));
      if (!pinned) {
        setResume(null);
        return;
      }
      const recovered = await getDraft(pinned);
      setResume(recovered);
    } catch {
      try {
        window.localStorage.removeItem(draftKey(employeeId));
      } catch {
        /* ignore */
      }
      setResume(null);
    }
  };

  const prevEmployee = useRef(employeeId);
  useEffect(() => {
    // Account switch: drop the previous owner's recovery pin so a
    // stale draft can never surface under a new account (pins are
    // also keyed per employee, and server drafts stay owner-scoped).
    if (prevEmployee.current && prevEmployee.current !== employeeId) {
      try {
        window.localStorage.removeItem(draftKey(prevEmployee.current));
      } catch {
        /* ignore */
      }
    }
    prevEmployee.current = employeeId;
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employeeId]);

  const openForFile = (file: File | null): void => {
    if (!file) return;
    if (!isVideoFile(file)) {
      setCardMsg(vu("wrongType"));
      return;
    }
    setCardMsg("");
    setPanel({ file });
  };

  const cancelDraft = async (id: string): Promise<void> => {
    setBusyDelete(true);
    try {
      await deleteDraft(id);
      setConfirmDelete(null);
      try {
        if (window.localStorage.getItem(draftKey(employeeId)) === id) {
          window.localStorage.removeItem(draftKey(employeeId));
        }
      } catch {
        /* ignore */
      }
      setResume((r) => (r?.id === id ? null : r));
      setToast(vu("deletedMsg"));
      await reload();
    } catch (e) {
      setCardMsg(vu("errorGeneric", { error: e instanceof Error ? e.message : String(e) }));
    } finally {
      setBusyDelete(false);
    }
  };

  const discardResume = async (): Promise<void> => {
    if (!resume) return;
    await cancelDraft(resume.id);
  };

  /** Cancel a running analysis job, then return the draft to
   *  needs_confirmation so it never strands in "analyzing". */
  const cancelAnalysis = async (d: DraftView): Promise<void> => {
    if (!d.live_job_id || busyCancel) return;
    setBusyCancel(true);
    try {
      await cancelAnalysisJob(d.live_job_id);
      await patchDraft(d.id, { status: "needs_confirmation" });
      setToast(vu("analysisCancelledMsg"));
      await reload();
    } catch (e) {
      setCardMsg(vu("errorGeneric", { error: e instanceof Error ? e.message : String(e) }));
    } finally {
      setBusyCancel(false);
    }
  };

  return (
    <>
      <section
        className={`panel vu-card${dragOver ? " vu-drop-over" : ""}`}
        aria-labelledby="vu-card-title"
        onDragOver={(e) => {
          if ([...e.dataTransfer.types].includes("Files")) {
            e.preventDefault();
            setDragOver(true);
          }
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          if ([...e.dataTransfer.types].includes("Files")) {
            e.preventDefault();
            setDragOver(false);
            openForFile(e.dataTransfer.files?.[0] ?? null);
          }
        }}
      >
        <div className="vu-head">
          <div style={{ flex: "1 1 auto", minWidth: 0 }}>
            <h2 className="panel-title" id="vu-card-title">{vu("title")}</h2>
            <p className="panel-sub">{vu("description")}</p>
            <p className="panel-sub">{vu("dropHint")}</p>
          </div>
          <div className="vu-actions">
            <button type="button" className="btn-primary" onClick={() => setPanel({})}>
              <Icon name="plus" size={16} /> {vu("uploadButton")}
            </button>
          </div>
        </div>
        {cardMsg ? <p role="status" className="muted" style={{ marginBottom: 0 }}>{cardMsg}</p> : null}
        {resume ? (
          <div className="chip-row" style={{ marginTop: 12 }}>
            <span className="chip-static">
              <strong>{vu("resumeTitle")}:&nbsp;</strong>
              {vu("resumeBody", {
                name: draftName(resume),
                date: fmtDate(resume.updated_at || resume.created_at),
              })}
            </span>
            <button type="button" className="btn-soft" onClick={() => setPanel({ draftId: resume.id })}>
              {vu("resumeButton")}
            </button>
            <button type="button" className="link-teal" onClick={() => void discardResume()}>
              {vu("discardButton")}
            </button>
          </div>
        ) : null}
      </section>

      <section className="panel" aria-labelledby="vu-recent-title">
        <div className="panel-head">
          <h2 className="panel-title" id="vu-recent-title">{vu("recentTitle")}</h2>
        </div>
        {!drafts && !draftsError ? (
          <Skeleton height={72} />
        ) : draftsError ? (
          <EmptyState text={draftsError} />
        ) : drafts && drafts.length ? (
          <ul className="plain" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {drafts.slice(0, 5).map((d) => {
              const primary = TERMINAL_VIEW.includes(d.status)
                ? { stage: "review" as const, label: vu("viewBtn") }
                : RETRYABLE.includes(d.status)
                  ? { stage: "video" as const, label: vu("retryBtn") }
                  : { stage: undefined, label: vu("continueBtn") };
              return (
                <li
                  key={d.id}
                  style={{
                    display: "flex", alignItems: "center", gap: 12,
                    padding: "10px 0", borderBottom: "1px solid var(--shell-line)",
                    flexWrap: "wrap",
                  }}
                >
                  <CreativeThumb
                    seed={draftSeed(d)}
                    label={draftName(d)}
                  />
                  <span style={{ flex: "1 1 180px", minWidth: 0 }}>
                    <span className="cell-main" style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {draftName(d)}
                    </span>
                    <span className="cell-sub" style={{ display: "block" }}>
                      {[d.spec?.campaign, fmtDate(d.updated_at || d.created_at)]
                        .filter(Boolean).join(" · ")}
                    </span>
                  </span>
                  <span className="pill pill-info">{statusName(d.status)}</span>
                  {d.live_job_id ? (
                    <button
                      type="button" className="btn-outline btn-compact" disabled={busyCancel}
                      onClick={() => void cancelAnalysis(d)}
                    >
                      {vu("cancelAnalysisBtn")}
                    </button>
                  ) : null}
                  {confirmDelete === d.id ? (
                    <span className="row-actions" role="group" aria-label={vu("confirmCancelTitle")}>
                      <span className="cell-sub">{vu("confirmCancelTitle")}</span>
                      <button
                        type="button" className="btn-outline btn-compact" disabled={busyDelete}
                        onClick={() => void cancelDraft(d.id)}
                      >
                        {vu("deleteBtn")}
                      </button>
                      <button
                        type="button" className="link-teal" disabled={busyDelete}
                        onClick={() => setConfirmDelete(null)}
                      >
                        {vu("keepBtn")}
                      </button>
                    </span>
                  ) : (
                    <span className="row-actions">
                      <button
                        type="button" className="btn-soft btn-compact"
                        onClick={() => setPanel(
                          primary.stage ? { draftId: d.id, stage: primary.stage } : { draftId: d.id },
                        )}
                      >
                        {primary.label}
                      </button>
                      <button
                        type="button" className="icon-btn" aria-label={`${vu("cancelBtn")}: ${draftName(d)}`}
                        style={{ width: 30, height: 30 }}
                        onClick={() => setConfirmDelete(d.id)}
                      >
                        <Icon name="x" size={15} />
                      </button>
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <EmptyState compact verbatim icon="play" text={vu("recentEmpty")} />
        )}
      </section>

      {panel ? (
        <VideoUploadPanel
          open={panel}
          employeeId={employeeId}
          onClose={(refresh) => {
            setPanel(null);
            if (refresh) void reload();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
    </>
  );
}
