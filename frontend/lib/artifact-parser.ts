import type { Artifact } from "@/lib/types";

const artifactPattern = /<artifact\s+type=["']([^"']+)["']\s*>([\s\S]*?)<\/artifact>/i;
export function parseArtifact(content: string): { visibleContent: string; artifact: Artifact | null } {
  const match = artifactPattern.exec(content);
  if (!match) return { visibleContent: content, artifact: null };
  return { visibleContent: content.replace(match[0], "").trim(), artifact: { type: match[1].toLowerCase(), content: match[2].trim() } };
}
