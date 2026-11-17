import { QueryClient } from "@tanstack/react-query";
import { session } from "./session/store";
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: false,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
});
session.onStop(() => {
  void queryClient.cancelQueries();
  queryClient.clear();
});
export const key = (...parts: (string | number)[]) => [
  session.get().owner,
  ...parts,
];
