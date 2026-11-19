import type { Model } from "../api/client";

export class IdentityContractError extends Error {
  constructor() {
    super(
      "学习服务返回的账号信息格式不正确，请联系管理员检查接口后，从官网重新进入。",
    );
    this.name = "IdentityContractError";
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

// TypeScript checks our code at build time. This checks the actual server reply
// before an identity can own any cached learning data or business requests.
export function parseIdentity(value: unknown): Model<"MeOut"> {
  if (
    !record(value) ||
    typeof value.userId !== "string" ||
    !value.userId.trim() ||
    /[\r\n]/.test(value.userId) ||
    typeof value.displayName !== "string" ||
    !record(value.capabilities) ||
    !Object.values(value.capabilities).every(
      (item) => typeof item === "boolean",
    ) ||
    (value.storage != null &&
      (!record(value.storage) ||
        !Object.values(value.storage).every(
          (item) =>
            typeof item === "number" && Number.isSafeInteger(item) && item >= 0,
        )))
  )
    throw new IdentityContractError();

  return {
    userId: value.userId,
    displayName: value.displayName || value.userId,
    capabilities: Object.fromEntries(
      Object.entries(value.capabilities),
    ) as Record<string, boolean>,
    storage:
      value.storage == null
        ? null
        : ({ ...value.storage } as Record<string, number>),
  };
}
