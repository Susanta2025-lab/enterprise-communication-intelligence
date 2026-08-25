import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import type { EciApiClient } from "./api/client";
import { HomePage } from "./pages/HomePage";
import { createQueryClient } from "./query/queryClient";

type AppProps = {
  apiClient: EciApiClient;
};

export function App({ apiClient }: AppProps) {
  const [queryClient] = useState(() => createQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <HomePage apiClient={apiClient} />
    </QueryClientProvider>
  );
}
