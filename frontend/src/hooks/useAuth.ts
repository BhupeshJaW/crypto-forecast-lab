import { useSyncExternalStore } from "react";
import { authStore } from "../services/authToken";

export function useAuth() {
  const state = useSyncExternalStore(authStore.subscribe, authStore.getState, authStore.getState);
  return { ...state, store: authStore };
}
