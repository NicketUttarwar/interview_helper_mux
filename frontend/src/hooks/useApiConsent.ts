import { useCallback } from "react";
import { api } from "../api/client";
import type { ApiProvider } from "../types";
import { useApp } from "../context/AppContext";

export function useApiConsent() {
  const { apiGrants, apiProviders, grantApiConsent, refreshApiGrants } = useApp();

  const consentsForExecute = useCallback(() => ({ ...apiGrants }), [apiGrants]);

  const loadProviders = useCallback(async () => {
    const data = await api<{ providers: ApiProvider[]; grants: Record<string, boolean> }>(
      "/api/session/api-consent",
    );
    return data;
  }, []);

  return {
    apiGrants,
    apiProviders,
    grantApiConsent,
    refreshApiGrants,
    consentsForExecute,
    loadProviders,
  };
}
