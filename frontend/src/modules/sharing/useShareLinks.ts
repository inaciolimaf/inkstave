/** State and mutations for the "Share with a link" section (spec 116). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { createShareLink, listShareLinks, revokeShareLink } from "./api";
import type { LinkRole, ShareLink } from "./types";

export function useShareLinks(projectId: string, enabled: boolean) {
  const { t } = useTranslation("sharing");
  const qc = useQueryClient();
  // A raw URL exists only in the session that created the link: after a reload the row says
  // "Link on" and offers Rotate, which makes a new one.
  const [urls, setUrls] = useState<Partial<Record<LinkRole, string>>>({});

  const linksQuery = useQuery({
    queryKey: ["share-links", projectId],
    queryFn: () => listShareLinks(projectId),
    enabled,
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["share-links", projectId] });
    void qc.invalidateQueries({ queryKey: ["members", projectId] });
  };

  // Creating a link for a role that already has one rotates it: the server revokes the old row.
  const create = useMutation({
    mutationFn: (role: LinkRole) => createShareLink(projectId, role),
    onSuccess: (link) => {
      setUrls((current) => ({ ...current, [link.role]: link.url }));
      invalidate();
    },
    onError: () => toast.error(t("links.saveError")),
  });

  const revoke = useMutation({
    mutationFn: (link: ShareLink) => revokeShareLink(projectId, link.id),
    onSuccess: (_, link) => {
      setUrls((current) => {
        const next = { ...current };
        delete next[link.role];
        return next;
      });
      invalidate();
    },
    onError: () => toast.error(t("links.saveError")),
  });

  const copy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success(t("links.copied"));
    } catch {
      toast.error(t("links.copyError"));
    }
  };

  return { linksQuery, links: linksQuery.data ?? [], urls, create, revoke, copy };
}
