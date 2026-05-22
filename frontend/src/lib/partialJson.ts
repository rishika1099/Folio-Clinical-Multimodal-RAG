/**
 * Tolerant partial-JSON parser. Walks the buffer, tracks brace/bracket
 * depth and string state, then closes any open structures so we get a
 * parse-able object even mid-stream. Good enough for showing fields as
 * they arrive without pulling in a full library.
 */
export function parsePartial(input: string): any | null {
  if (!input) return null;
  let s = input.trim();
  // strip ``` fences if present
  if (s.startsWith("```")) {
    s = s.replace(/^```(?:json)?/i, "").replace(/```$/, "");
  }
  // Trim to outermost {
  const start = s.indexOf("{");
  if (start === -1) return null;
  s = s.slice(start);

  // Track structure to know what closers we still need.
  let inStr = false;
  let escape = false;
  const stack: string[] = [];
  let lastNonWs = -1;

  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inStr) {
      if (escape) escape = false;
      else if (c === "\\") escape = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') { inStr = true; continue; }
    if (c === "{" || c === "[") stack.push(c);
    else if (c === "}") { if (stack[stack.length - 1] === "{") stack.pop(); }
    else if (c === "]") { if (stack[stack.length - 1] === "[") stack.pop(); }
    if (!/\s/.test(c)) lastNonWs = i;
  }

  let trimmed = s.slice(0, lastNonWs + 1);

  // If we're inside a string, close it.
  if (inStr) trimmed += '"';

  // If trailing char is a comma or colon, drop it.
  while (/[,:]\s*$/.test(trimmed)) {
    trimmed = trimmed.replace(/[,:]\s*$/, "");
  }

  // Close any open structures.
  while (stack.length) {
    const o = stack.pop()!;
    trimmed += o === "{" ? "}" : "]";
  }

  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}
