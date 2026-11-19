import { request, type Model, type Transport } from "./client";

export type UploadProgress = { loaded: number; total?: number };
type ProgressHandler = (progress: UploadProgress) => void;
type UploadAdapter = (onProgress: ProgressHandler) => Transport;
let previewAdapter: UploadAdapter | undefined;

// The isolated demo supplies its own adapter; production uses browser byte events.
export function setUploadAdapter(adapter: UploadAdapter) {
  previewAdapter = adapter;
}

export function xhrUpload(onProgress: ProgressHandler): Transport {
  return (input, init = {}) =>
    new Promise<Response>((resolve, reject) => {
      if (init.signal?.aborted)
        return reject(new DOMException("Aborted", "AbortError"));
      const xhr = new XMLHttpRequest();
      const abort = () => xhr.abort();
      const cleanup = () => init.signal?.removeEventListener("abort", abort);
      xhr.open(init.method || "POST", String(input));
      xhr.withCredentials = true;
      new Headers(init.headers).forEach((value, name) =>
        xhr.setRequestHeader(name, value),
      );
      xhr.upload.onprogress = (event) => {
        if (!init.signal?.aborted)
          onProgress({
            loaded: event.loaded,
            total: event.lengthComputable ? event.total : undefined,
          });
      };
      xhr.onload = () => {
        cleanup();
        const headers = new Headers();
        for (const line of xhr
          .getAllResponseHeaders()
          .trim()
          .split(/[\r\n]+/)) {
          const colon = line.indexOf(":");
          if (colon > 0)
            headers.append(line.slice(0, colon), line.slice(colon + 1).trim());
        }
        resolve(
          new Response(xhr.status === 204 ? null : xhr.responseText, {
            status: xhr.status,
            headers,
          }),
        );
      };
      xhr.onerror = () => {
        cleanup();
        reject(
          new TypeError("上传连接中断，请检查网络并刷新资料列表确认结果。"),
        );
      };
      xhr.onabort = () => {
        cleanup();
        reject(new DOMException("Aborted", "AbortError"));
      };
      init.signal?.addEventListener("abort", abort, { once: true });
      try {
        xhr.send(init.body as FormData);
      } catch (error) {
        cleanup();
        reject(error);
      }
    });
}

export function uploadMaterial(
  id: number,
  file: File,
  onProgress: ProgressHandler,
  signal?: AbortSignal,
) {
  const body = new FormData();
  body.append("file", file);
  // Reuse the account-bound response handling, session cancellation and error codes.
  return request<Model<"UploadOut">>(
    `/projects/${id}/materials`,
    { method: "POST", body },
    signal,
    "json",
    {
      transport: (previewAdapter || xhrUpload)(onProgress),
      timeoutMs: 5 * 60_000,
    },
  );
}
