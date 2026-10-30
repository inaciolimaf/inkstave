/** Single-flight project .zip download with per-project loading + error toast (spec 102). */
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { downloadProjectZip } from "./api";

export function useDownloadProject() {
  const { t } = useTranslation("projects");
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const download = useCallback(
    async (id: string, name: string) => {
      if (downloadingId) return; // ignore concurrent clicks while one is in flight
      setDownloadingId(id);
      try {
        await downloadProjectZip(id, name);
      } catch {
        toast.error(t("download.error"));
      } finally {
        setDownloadingId(null);
      }
    },
    [downloadingId, t],
  );

  return { download, downloadingId, isDownloading: downloadingId !== null };
}
