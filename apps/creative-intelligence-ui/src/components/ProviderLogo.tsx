import anthropic from "@/assets/providers/claude.svg";
import chatgpt from "@/assets/providers/openai.svg";
import deepseek from "@/assets/providers/deepseek.svg";
import gemini from "@/assets/providers/gemini.svg";
import glm from "@/assets/providers/glm.svg";
import grok from "@/assets/providers/grok.svg";
import groq from "@/assets/providers/groq.svg";
import kimi from "@/assets/providers/kimi.svg";
import litellm from "@/assets/providers/litellm.svg";
import meta from "@/assets/providers/meta.svg";
import nvidia from "@/assets/providers/nvidia.svg";
import ollama from "@/assets/providers/ollama.svg";
import openai from "@/assets/providers/openai.svg";
import openrouter from "@/assets/providers/openrouter.png";
import qwen from "@/assets/providers/qwen.svg";
import teamorouter from "@/assets/providers/teamorouter.svg";

/** Brand mark per provider id (mirrors the Nextly AI logo set).
 *  Unknown ids render nothing so the caller falls back to a glyph. */
const LOGOS: Record<string, string> = {
  anthropic,
  chatgpt,
  deepseek,
  gemini,
  glm,
  grok,
  groq,
  kimi,
  litellm,
  muse: meta,
  nvidia,
  ollama,
  openai,
  openrouter,
  qwen,
  teamorouter,
};

export function hasProviderLogo(id: string): boolean {
  return Boolean(LOGOS[id]);
}

export function ProviderLogo({ id, size = 22 }: { id: string; size?: number }) {
  const src = LOGOS[id];
  if (!src) return null;
  return <img className="provider-logo" src={src} width={size} height={size} alt="" draggable={false} />;
}
