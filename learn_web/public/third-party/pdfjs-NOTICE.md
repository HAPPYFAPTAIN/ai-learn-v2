# PDF preview

PDF.js (`pdfjs-dist` 6.5.438) is provided by Mozilla and contributors under
Apache-2.0: https://github.com/mozilla/pdf.js.

The matching parser worker is bundled locally by Vite; the preview UI and library
are loaded only when the reader selects PDF original preview. No CDN is used.

`scripts/prepare-pdf-assets.mjs` copies the package's LICENSE and the cmaps,
standard_fonts, wasm and iccs directories, including their license files, into
`public/pdfjs-assets/6.5.438/` before development or production builds. These
generated assets are ignored by Git and copied into the React static build.
Preserve this directory's license files when deploying that build.

The browser integration uses no Node canvas bindings. `@napi-rs/canvas` is an
optional dependency for upstream's Node integration and is not used or shipped
by this frontend. No runtime resource is added to the legacy release policy.
