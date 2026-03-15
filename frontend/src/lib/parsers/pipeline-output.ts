export type ParsedIterationFile = {
  path: string;
  content: string;
};

export type ParsedIteration = {
  iterationLabel: string;
  summary?: string;
  files: ParsedIterationFile[];
  rawJson: string;
};

export type ParsedPipelineOutput = {
  iterations: ParsedIteration[];
  raw: string;
};

function safeParseJson(value: string): unknown | null {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function fromJsonPayload(payload: unknown, label: string, rawJson: string): ParsedIteration | null {
  if (!payload || typeof payload !== 'object') return null;

  const maybeSummary = (payload as { summary?: unknown }).summary;
  const summary = typeof maybeSummary === 'string' ? maybeSummary : undefined;

  const maybeFiles = (payload as { files?: unknown }).files;
  const files = Array.isArray(maybeFiles)
    ? maybeFiles
        .map((item) => {
          if (!item || typeof item !== 'object') return null;
          const path = (item as { path?: unknown }).path;
          const content = (item as { content?: unknown }).content;
          if (typeof path !== 'string' || typeof content !== 'string') return null;
          return { path, content };
        })
        .filter((item): item is ParsedIterationFile => item !== null)
    : [];

  return {
    iterationLabel: label,
    summary,
    files,
    rawJson
  };
}

export function parsePipelineOutput(raw: string): ParsedPipelineOutput {
  const text = raw?.trim() ?? '';
  if (!text) return { iterations: [], raw: '' };

  const iterations: ParsedIteration[] = [];
  const iterationRegex = /===\s*(Iteration\s*\d+)\s*===\s*```json\s*([\s\S]*?)```/g;

  for (const match of text.matchAll(iterationRegex)) {
    const label = match[1]?.trim() || 'Iteration';
    const rawJson = (match[2] || '').trim();
    const parsed = safeParseJson(rawJson);
    const mapped = fromJsonPayload(parsed, label, rawJson);
    if (mapped) iterations.push(mapped);
  }

  if (iterations.length > 0) {
    return { iterations, raw: text };
  }

  const fencedJsonMatch = text.match(/```json\s*([\s\S]*?)```/);
  if (fencedJsonMatch?.[1]) {
    const rawJson = fencedJsonMatch[1].trim();
    const parsed = safeParseJson(rawJson);
    const mapped = fromJsonPayload(parsed, 'Iteration 1', rawJson);
    if (mapped) return { iterations: [mapped], raw: text };
  }

  const directParsed = safeParseJson(text);
  const mappedDirect = fromJsonPayload(directParsed, 'Iteration 1', text);
  if (mappedDirect) return { iterations: [mappedDirect], raw: text };

  return { iterations: [], raw: text };
}

