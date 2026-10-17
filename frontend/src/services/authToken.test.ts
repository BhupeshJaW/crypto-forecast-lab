import test from "node:test";
import assert from "node:assert/strict";
import { createAuthStore } from "./authToken";

const memStorage = () => {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k), m };
};

test("token is memory-only unless 'remember' is chosen", () => {
  const st = memStorage();
  const s = createAuthStore(st);
  s.setToken("  abc  ", false);
  assert.equal(s.getToken(), "abc");
  assert.equal(st.m.size, 0);
  s.setToken("abc", true);
  assert.equal(st.m.size, 1);
});

test("a remembered token is restored; clear() removes it", () => {
  const st = memStorage();
  createAuthStore(st).setToken("abc", true);
  const s2 = createAuthStore(st);
  assert.equal(s2.getToken(), "abc");
  s2.clear();
  assert.equal(s2.getToken(), null);
  assert.equal(st.m.size, 0);
});

test("markRejected flags once; setToken clears the flag and bumps version", () => {
  const s = createAuthStore(null);
  let n = 0;
  s.subscribe(() => n++);
  s.markRejected();
  s.markRejected();
  assert.equal(n, 1);
  assert.equal(s.getState().rejected, true);
  const v = s.getState().version;
  s.setToken("x", false);
  assert.equal(s.getState().rejected, false);
  assert.equal(s.getState().version, v + 1);
});

test("empty token is ignored; broken storage does not throw", () => {
  const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); }, removeItem: () => { throw new Error("blocked"); } };
  const s = createAuthStore(broken);
  s.setToken("   ", true);
  assert.equal(s.getToken(), null);
  s.setToken("ok", true);
  assert.equal(s.getToken(), "ok");
});
