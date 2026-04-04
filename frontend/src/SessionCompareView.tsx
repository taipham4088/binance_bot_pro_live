import { useEffect, useState } from "react";
import { SessionComparePanel } from "./replay/SessionComparePanel";
import { Divergence } from "./replay/session_compare";

export function SessionCompareView() {
  const [divergence, setDivergence] = useState<Divergence | null>(null);

  useEffect(() => {
    // dùng sessionStore đang chạy (debug hook)
    const store = (window as any).__sessionStore;
    if (!store) return;

    // chạy compare mỗi khi state thay đổi
    const unsub = store.subscribe(() => {
      const d = store.compareWithReplay();
      setDivergence(d);
    });

    return unsub;
  }, []);

  return <SessionComparePanel divergence={divergence} />;
}
