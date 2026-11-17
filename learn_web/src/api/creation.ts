export type CreationIntent = { signature: string; requestId: string };

// Keep an intent through uncertain retries; clear it after confirmed success.
// A new UUID, rather than identical content, distinguishes a deliberate duplicate.
export function creationRequest<T extends object>(
  intent: { current: CreationIntent | undefined },
  payload: T,
): T & { requestId: string } {
  const signature = JSON.stringify(payload);
  if (intent.current?.signature !== signature)
    intent.current = { signature, requestId: crypto.randomUUID() };
  return { ...payload, requestId: intent.current.requestId };
}
