/* Tiny word-level diff utility for comparing OS-run summaries.

   No external dependency — implements a Longest Common Subsequence
   (LCS) walk that's plenty fast for the short (<2KB) summary strings
   the Marketing OS produces.

   Strategy: tokenize on whitespace (preserving \n as its own token
   so paragraph structure survives), LCS over word tokens, then
   render with a single space between consecutive tokens. The
   "newline-as-token" trick gives us clean multi-line rendering
   without managing whitespace runs explicitly.

   Output: `[{ type: 'eq'|'add'|'del', text: string }, ...]`
   coalesced so consecutive same-type tokens are merged. */

const NL = '\n';

const _tokenize = (s) => {
  if (!s) return [];
  // Each \n is its own token; runs of whitespace collapse to a
  // single separator between word tokens.
  const out = [];
  for (const line of s.split('\n')) {
    const words = line.split(/\s+/).filter(Boolean);
    out.push(...words);
    out.push(NL);
  }
  // Trim a trailing newline so the output doesn't end on an empty line.
  while (out.length && out[out.length - 1] === NL) out.pop();
  return out;
};


export function wordDiff(oldStr, newStr) {
  const a = _tokenize(oldStr);
  const b = _tokenize(newStr);
  const N = a.length, M = b.length;

  // LCS DP table. Stored as Uint16 so 65k tokens still fit fine.
  const dp = Array.from({ length: N + 1 }, () => new Uint16Array(M + 1));
  for (let i = N - 1; i >= 0; i--) {
    for (let j = M - 1; j >= 0; j--) {
      if (a[i] === b[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const ops = [];
  let i = 0, j = 0;
  while (i < N && j < M) {
    if (a[i] === b[j]) {
      ops.push({ type: 'eq', text: a[i] });
      i++; j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ type: 'del', text: a[i] });
      i++;
    } else {
      ops.push({ type: 'add', text: b[j] });
      j++;
    }
  }
  while (i < N) ops.push({ type: 'del', text: a[i++] });
  while (j < M) ops.push({ type: 'add', text: b[j++] });

  // Render tokens back into displayable strings, joining word tokens
  // with a leading space EXCEPT when the previous emit was a newline
  // (which would create awkward " " at line starts).
  const out = [];
  let prevWasNL = true;  // start of stream — no leading space needed
  for (const op of ops) {
    let text;
    if (op.text === NL) {
      text = NL;
      prevWasNL = true;
    } else {
      text = (prevWasNL ? '' : ' ') + op.text;
      prevWasNL = false;
    }
    out.push({ type: op.type, text });
  }
  // Coalesce consecutive same-type tokens for tighter rendering.
  const compact = [];
  for (const r of out) {
    const last = compact[compact.length - 1];
    if (last && last.type === r.type) last.text += r.text;
    else compact.push({ ...r });
  }
  return compact;
}
