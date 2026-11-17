# Content rendering

These libraries are bundled locally by Vite, with versions pinned in package-lock.json.
No CDN or remote model-supplied scripts are loaded.

- @markmap/parse, @markmap/view, @markmap/core and @markmap/render 1.1.0:
  https://github.com/markmap/markmap — MIT; see markmap-LICENSE.txt.
- rehype-highlight 7.0.2:
  https://github.com/rehypejs/rehype-highlight — MIT; see rehype-highlight-LICENSE.txt.
- highlight.js (via lowlight):
  https://github.com/highlightjs/highlight.js — BSD-3-Clause; see highlight-js-LICENSE.txt.

Full notices for all packages newly introduced by these features (including D3,
YAML, lowlight and Markdown utilities) are preserved in dependencies-LICENSES.txt.

This directory accompanies the React static build. It does not add resources to the
legacy Gradio release package or change runtime/release-policy.json.
