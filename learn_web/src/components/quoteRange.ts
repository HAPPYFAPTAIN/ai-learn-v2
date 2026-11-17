// Build ranges without inserting markup into React-owned lesson text.
export function readingIndex(root: HTMLElement) {
  const nodes = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const positions: { node: Text; offset: number }[] = [];
  let text = "";
  let item;
  while ((item = nodes.nextNode())) {
    const node = item as Text;
    if (
      node.parentElement?.closest(
        'button, [aria-hidden="true"], .katex-mathml, .code-block-toolbar, [hidden]',
      )
    )
      continue;
    for (let i = 0; i < node.length; i++) {
      if (/\s/.test(node.data[i])) continue;
      positions.push({ node, offset: i });
      text += node.data[i];
    }
  }
  return { text, positions };
}
export function matchingRanges(
  index: ReturnType<typeof readingIndex>,
  quote: string,
  limit = 200,
  ignoreCase = false,
) {
  const needle = quote.replace(/\s/g, "");
  const ranges: Range[] = [];
  if (!needle) return { ranges, truncated: false };
  // Locale-independent per-character folding avoids changing offsets (e.g. dotted I).
  const fold = (text: string) =>
    text.replace(/[A-Z]/g, (char) => char.toLowerCase());
  const haystack = ignoreCase ? fold(index.text) : index.text;
  const target = ignoreCase ? fold(needle) : needle;
  let at = haystack.indexOf(target);
  while (at >= 0 && ranges.length < limit) {
    const first = index.positions[at],
      last = index.positions[at + needle.length - 1];
    const range = document.createRange();
    range.setStart(first.node, first.offset);
    range.setEnd(last.node, last.offset + 1);
    ranges.push(range);
    at = haystack.indexOf(target, at + 1);
  }
  return { ranges, truncated: at >= 0 };
}
// Quoted text is the existing contract, not a stable cross-version anchor.
export function quoteRange(
  root: HTMLElement,
  quote: string,
): { range?: Range; ambiguous: boolean } {
  const { ranges } = matchingRanges(readingIndex(root), quote, 2);
  return {
    range: ranges.length === 1 ? ranges[0] : undefined,
    ambiguous: ranges.length > 1,
  };
}
