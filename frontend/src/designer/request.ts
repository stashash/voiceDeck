/** Deadlines include reading the response body. Never retry mutations automatically. */
export function request(input: RequestInfo | URL, init: RequestInit = {}, timeoutMs=20_000): Promise<Response> {
  const timeout = AbortSignal.timeout(timeoutMs);
  return fetch(input, {...init, signal: init.signal ? AbortSignal.any([init.signal, timeout]) : timeout});
}
