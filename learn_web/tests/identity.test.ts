import { beforeEach, expect, it } from "vitest";
import { IdentityContractError, parseIdentity } from "../src/session/identity";
import { session } from "../src/session/store";
import { queryClient, key } from "../src/query";

const valid = {
  userId: "account-a",
  displayName: "学习者",
  capabilities: { chat: true, streamChat: false },
  storage: null,
};
beforeEach(() => {
  sessionStorage.clear();
  session.reset();
  queryClient.clear();
});

it("accepts existing identity replies, optional storage and future capability keys", () => {
  expect(parseIdentity(valid)).toEqual(valid);
  expect(
    parseIdentity({
      ...valid,
      displayName: "",
      storage: undefined,
      futureField: "ignored",
    }),
  ).toEqual({ ...valid, displayName: valid.userId });
  expect(
    parseIdentity({
      ...valid,
      capabilities: { nextFeature: false },
      storage: { usedBytes: 100, quotaBytes: 200 },
    }).storage,
  ).toEqual({ usedBytes: 100, quotaBytes: 200 });
});

it.each([
  null,
  [],
  { ...valid, userId: "" },
  { ...valid, userId: 7 },
  { ...valid, userId: "injected\r\nHeader: value" },
  { ...valid, displayName: null },
  { ...valid, capabilities: [] },
  { ...valid, capabilities: { chat: "true" } },
  { ...valid, storage: { usedBytes: -1 } },
  { ...valid, storage: { usedBytes: "100" } },
  { ...valid, storage: { usedBytes: Infinity } },
])(
  "rejects malformed identity data before creating an account scope: %j",
  (reply) => {
    expect(() => parseIdentity(reply)).toThrow(IdentityContractError);
    session.ready(reply);
    expect(session.get().status).toBe("blocked");
    expect(session.get().owner).toBe("");
    expect(sessionStorage.getItem("learn.v2.page-owner")).toBeNull();
  },
);

it("clears an existing account's cached data if a renewed identity reply becomes invalid", () => {
  session.ready(valid);
  queryClient.setQueryData(key("projects"), { private: "saved data" });
  session.ready({ ...valid, capabilities: "invalid" });
  expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  expect(session.signal().aborted).toBe(true);
});
