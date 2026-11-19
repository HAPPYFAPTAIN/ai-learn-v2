import { beforeEach, expect, it, vi } from "vitest";
import { uploadMaterial } from "../src/api/upload";
import { session } from "../src/session/store";

class FakeXHR {
  static all: FakeXHR[] = [];
  upload: {
    onprogress?: (event: {
      loaded: number;
      total: number;
      lengthComputable: boolean;
    }) => void;
  } = {};
  status = 202;
  responseText = '{"fileId":"one","sizeBytes":10,"sha256":"test","jobId":null}';
  withCredentials = false;
  headers = new Headers();
  url = "";
  body?: FormData;
  onload?: () => void;
  onerror?: () => void;
  onabort?: () => void;
  constructor() {
    FakeXHR.all.push(this);
  }
  open(_method: string, url: string) {
    this.url = url;
  }
  setRequestHeader(name: string, value: string) {
    this.headers.set(name, value);
  }
  getAllResponseHeaders() {
    return "content-type: application/json\r\nx-learn-error: ACCOUNT_CHANGED";
  }
  send(body: FormData) {
    this.body = body;
  }
  abort = vi.fn(() => this.onabort?.());
}
beforeEach(() => {
  sessionStorage.clear();
  session.reset();
  session.ready({ userId: "alice", displayName: "Alice", capabilities: {} });
  FakeXHR.all = [];
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
});
const file = () => new File(["hello"], "lesson.txt", { type: "text/plain" });
it("uploads multipart data with the verified page owner and reports real byte events", async () => {
  const progress = vi.fn();
  const pending = uploadMaterial(1, file(), progress);
  const xhr = FakeXHR.all[0];
  expect(xhr.url).toBe("/api/v2/projects/1/materials");
  expect(xhr.withCredentials).toBe(true);
  expect(xhr.headers.get("X-Learn-Expected-User")).toBe("alice");
  expect(xhr.headers.has("Content-Type")).toBe(false);
  expect((xhr.body!.get("file") as File).name).toBe("lesson.txt");
  xhr.upload.onprogress!({ loaded: 4, total: 10, lengthComputable: true });
  expect(progress).toHaveBeenLastCalledWith({ loaded: 4, total: 10 });
  xhr.upload.onprogress!({ loaded: 5, total: 0, lengthComputable: false });
  expect(progress).toHaveBeenLastCalledWith({ loaded: 5, total: undefined });
  xhr.onload!();
  await expect(pending).resolves.toMatchObject({ fileId: "one" });
});
it("cancels an active upload and discards subsequent byte events when the account stops", async () => {
  const progress = vi.fn();
  const pending = uploadMaterial(1, file(), progress);
  const rejected = expect(pending).rejects.toMatchObject({
    name: "AbortError",
  });
  const xhr = FakeXHR.all[0];
  session.stop("changed");
  xhr.upload.onprogress!({ loaded: 10, total: 10, lengthComputable: true });
  await rejected;
  expect(xhr.abort).toHaveBeenCalledTimes(1);
  expect(progress).not.toHaveBeenCalled();
});
it("does not create an upload for an already aborted request", async () => {
  const abort = new AbortController();
  abort.abort();
  await expect(
    uploadMaterial(1, file(), vi.fn(), abort.signal),
  ).rejects.toMatchObject({ name: "AbortError" });
  expect(FakeXHR.all).toHaveLength(0);
});
it("applies the shared account-change handling to upload responses", async () => {
  const pending = uploadMaterial(1, file(), vi.fn());
  const rejected = expect(pending).rejects.toMatchObject({
    code: "ACCOUNT_CHANGED",
  });
  FakeXHR.all[0].status = 409;
  FakeXHR.all[0].onload!();
  await rejected;
  expect(session.get().status).toBe("blocked");
});
it("exposes server failures without automatically repeating the upload", async () => {
  const pending = uploadMaterial(1, file(), vi.fn());
  const rejected = expect(pending).rejects.toMatchObject({
    code: "STORAGE_FULL",
    status: 507,
  });
  FakeXHR.all[0].status = 507;
  FakeXHR.all[0].responseText =
    '{"error":{"code":"STORAGE_FULL","message":"空间不足"}}';
  FakeXHR.all[0].onload!();
  await rejected;
  expect(FakeXHR.all).toHaveLength(1);
  expect(session.get().status).toBe("ready");
});
