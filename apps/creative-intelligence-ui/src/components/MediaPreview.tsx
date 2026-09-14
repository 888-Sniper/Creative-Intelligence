import { useEffect, useState } from "react";
import type { RefObject } from "react";
import { api } from "@/api/client";
import { useLocale } from "@/i18n";

export type MediaKind = "video" | "audio" | "image";

/** Resolved mimes per media URL (one by-creative listing per creative). */
const mimeCache = new Map<string, string>();

const VIDEO_EXTS = ["mp4", "mov", "webm", "m4v", "ogv"];
const AUDIO_EXTS = ["mp3", "wav", "m4a", "ogg", "opus", "flac"];
const IMAGE_EXTS = ["png", "jpg", "jpeg", "webp", "gif", "svg", "avif", "bmp"];

/** Best-known kind for a preview URL: exact mime first, extension sniff
 *  for remote URLs, legacy <video> fallback (previous behaviour). */
export function kindForUrl(url: string, mime = ""): MediaKind {
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("audio/")) return "audio";
  if (mime.startsWith("image/")) return "image";
  const ext = url.split("?")[0].split(".").pop()?.toLowerCase() ?? "";
  if (VIDEO_EXTS.includes(ext)) return "video";
  if (AUDIO_EXTS.includes(ext)) return "audio";
  if (IMAGE_EXTS.includes(ext)) return "image";
  return "video";
}

function useMediaMime(src: string, creativeKey: string): string | null {
  const [mime, setMime] = useState<string | null>(() => mimeCache.get(src) ?? null);
  useEffect(() => {
    if (!src.startsWith("/media/")) return;
    const cached = mimeCache.get(src);
    if (cached !== undefined) {
      setMime(cached);
      return;
    }
    let live = true;
    api<{ media: Array<{ url: string; mime: string }> }>(
      "GET", `/media/by-creative/${encodeURIComponent(creativeKey)}`,
    )
      .then((r) => {
        const found = (r.media ?? []).find((m) => m.url === src)?.mime ?? "";
        mimeCache.set(src, found);
        if (live) setMime(found);
      })
      .catch(() => {
        if (live) setMime("");
      });
    return () => {
      live = false;
    };
  }, [src, creativeKey]);
  return mime;
}

export interface MediaPreviewProps {
  src: string;
  creativeKey: string;
  /** Detail player: forwarded ref + stable test id. */
  videoRef?: RefObject<HTMLVideoElement | null>;
  testId?: string;
  /** Grid card style: muted inline preview, click toggles playback. */
  mutedPreview?: boolean;
}

/** Preview tag matched to the real media kind: video/audio/image. */
export function MediaPreview({ src, creativeKey, videoRef, testId, mutedPreview }: MediaPreviewProps) {
  const { t } = useLocale();
  const mime = useMediaMime(src, creativeKey);
  const kind = kindForUrl(src, mime ?? "");
  if (kind === "audio") {
    return <audio controls preload="metadata" src={src} style={{ width: "100%" }} data-testid={testId} />;
  }
  if (kind === "image") {
    return <img src={src} alt="" style={{ maxWidth: "100%" }} data-testid={testId} />;
  }
  if (mutedPreview) {
    return (
      <video
        muted
        playsInline
        preload="metadata"
        src={src}
        title={t("creatives.previewTitle")}
        data-testid={testId}
        onClick={(e) => {
          const v = e.currentTarget;
          if (v.paused) void v.play().catch(() => undefined);
          else v.pause();
        }}
      />
    );
  }
  return (
    <video
      id={testId === "creative-video" ? "creative-video" : undefined}
      data-testid={testId}
      ref={videoRef}
      controls
      preload="metadata"
      style={{ maxWidth: "100%" }}
    >
      <source src={src} />
    </video>
  );
}
