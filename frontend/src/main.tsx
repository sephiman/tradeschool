import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/lib/theme";
import { AuthProvider } from "@/auth/AuthContext";
import App from "./App";
import i18n from "@/i18n";
import { asApiError } from "@/api/client";
import { showToast } from "@/lib/toastBus";
import "./index.css";

interface MutationMeta {
  silentSuccess?: boolean;
  silentError?: boolean;
  successMessage?: string;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, staleTime: 30_000, retry: 1 },
  },
  queryCache: new QueryCache({
    onError: (error, query) => {
      if ((query.meta as { silentError?: boolean } | undefined)?.silentError) return;
      const api = asApiError(error);
      showToast(i18n.t(`errors.${api.code}`, api.message), "error");
    },
  }),
  mutationCache: new MutationCache({
    onSuccess: (_data, _vars, _ctx, mutation) => {
      const meta = mutation.options.meta as MutationMeta | undefined;
      if (meta?.silentSuccess) return;
      showToast(i18n.t(meta?.successMessage ?? "common.saved"), "success");
    },
    onError: (error, _vars, _ctx, mutation) => {
      const meta = mutation.options.meta as MutationMeta | undefined;
      if (meta?.silentError) return;
      const api = asApiError(error);
      showToast(i18n.t(`errors.${api.code}`, api.message), "error");
    },
  }),
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
