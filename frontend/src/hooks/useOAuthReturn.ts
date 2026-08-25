import { useEffect, useState } from "react";

import { oauthReturnMessage, parseOAuthReturnSearch, stripOAuthReturnParams } from "../oauth/returnParams";

export function useOAuthReturn() {
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [shouldRefresh, setShouldRefresh] = useState(false);

  useEffect(() => {
    const parsed = parseOAuthReturnSearch(window.location.search);
    if (parsed === null) {
      return;
    }
    setNotice(oauthReturnMessage(parsed));
    setShouldRefresh(true);
    const nextSearch = stripOAuthReturnParams(window.location.search);
    const nextUrl = `${window.location.pathname}${nextSearch}${window.location.hash}`;
    window.history.replaceState(null, "", nextUrl);
  }, []);

  return { notice, shouldRefresh };
}
