import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

interface SegmentRef {
  id: number;
  slug: string;
  title_ru: string;
  emoji?: string;
}

interface ProfilePayload {
  target_lead: string;
  accept_examples: string[];
  reject_examples: string[];
  conflict_slugs: string[];
  requires_llm: boolean;
  version?: number;
  locale?: string;
}

interface ProfileResponse {
  segment: SegmentRef;
  profile: {
    id: number;
    version: number;
    has_draft: boolean;
    published: ProfilePayload;
    draft: ProfilePayload | null;
    diff: Record<string, { before: unknown; after: unknown }>;
  } | null;
}

function linesToList(text: string): string[] {
  return text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

function listToLines(items: string[] | undefined): string {
  return (items ?? []).join("\n");
}

export function LlmProfileEditor({ segment }: { segment: SegmentRef }) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery<ProfileResponse>({
    queryKey: ["segment-llm-profile", segment.id],
    queryFn: () => api(`/api/segments/${segment.id}/llm-profile`),
  });

  const published = data?.profile?.published;
  const draft = data?.profile?.draft;
  const source = draft ?? published;

  const [targetLead, setTargetLead] = useState("");
  const [acceptText, setAcceptText] = useState("");
  const [rejectText, setRejectText] = useState("");
  const [conflictsText, setConflictsText] = useState("");
  const [requiresLlm, setRequiresLlm] = useState(true);
  const [reason, setReason] = useState("");
  const [previewText, setPreviewText] = useState("");
  const [previewResult, setPreviewResult] = useState<string>("");
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    setInitialized(false);
  }, [segment.id]);

  useEffect(() => {
    if (!source || initialized) return;
    setTargetLead(source.target_lead || "");
    setAcceptText(listToLines(source.accept_examples));
    setRejectText(listToLines(source.reject_examples));
    setConflictsText(listToLines(source.conflict_slugs));
    setRequiresLlm(Boolean(source.requires_llm));
    setInitialized(true);
  }, [source, initialized]);

  const payload = useMemo(
    () => ({
      target_lead: targetLead,
      accept_examples: linesToList(acceptText),
      reject_examples: linesToList(rejectText),
      conflict_slugs: linesToList(conflictsText),
      requires_llm: requiresLlm,
      locale: "ru",
    }),
    [targetLead, acceptText, rejectText, conflictsText, requiresLlm],
  );

  const diffEntries = Object.entries(data?.profile?.diff || {});

  const saveDraft = useMutation({
    mutationFn: () =>
      api(`/api/segments/${segment.id}/llm-profile/draft`, {
        method: "PUT",
        body: JSON.stringify({ ...payload, reason: reason || "draft" }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segment-llm-profile", segment.id] });
      toast.success("Черновик сохранён (published не изменён)");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const createProfile = useMutation({
    mutationFn: () =>
      api(`/api/segments/${segment.id}/llm-profile`, {
        method: "POST",
        body: JSON.stringify({ ...payload, reason: reason || "create" }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segment-llm-profile", segment.id] });
      toast.success("Профиль создан");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const publish = useMutation({
    mutationFn: () => {
      if (!window.confirm("Опубликовать черновик в runtime-профиль? Это опасное действие.")) {
        return Promise.reject(new Error("Отменено"));
      }
      if (!reason.trim()) {
        return Promise.reject(new Error("Укажите reason для publish"));
      }
      return api(`/api/segments/${segment.id}/llm-profile/publish`, {
        method: "POST",
        body: JSON.stringify({ confirm: true, reason, locale: "ru" }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segment-llm-profile", segment.id] });
      toast.success("Профиль опубликован");
    },
    onError: (e: Error) => {
      if (e.message !== "Отменено") toast.error(e.message);
    },
  });

  const rollback = useMutation({
    mutationFn: () => {
      if (!window.confirm("Откатить к предыдущей published-версии?")) {
        return Promise.reject(new Error("Отменено"));
      }
      if (!reason.trim()) {
        return Promise.reject(new Error("Укажите reason для rollback"));
      }
      return api(`/api/segments/${segment.id}/llm-profile/rollback`, {
        method: "POST",
        body: JSON.stringify({ confirm: true, reason, locale: "ru" }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segment-llm-profile", segment.id] });
      setInitialized(false);
      toast.success("Откат выполнен");
    },
    onError: (e: Error) => {
      if (e.message !== "Отменено") toast.error(e.message);
    },
  });

  const preview = useMutation({
    mutationFn: async () =>
      api(`/api/segments/${segment.id}/llm-profile/preview`, {
        method: "POST",
        body: JSON.stringify({ text: previewText, locale: "ru" }),
      }) as Promise<{
        offline_decision: string;
        offline_intent: string;
        may_bypass_llm: boolean;
        using_draft: boolean;
        note: string;
      }>,
    onSuccess: (res) => {
      setPreviewResult(
        `${res.offline_decision}/${res.offline_intent} · bypass=${res.may_bypass_llm} · draft=${res.using_draft}\n${res.note}`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }

  if (!data?.profile) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">
          У сегмента ещё нет LLM-профиля. Создайте published-версию v1.
        </p>
        <Label>target_lead</Label>
        <Textarea value={targetLead} onChange={(e) => setTargetLead(e.target.value)} />
        <Label>accept examples (по строке)</Label>
        <Textarea value={acceptText} onChange={(e) => setAcceptText(e.target.value)} className="min-h-24 font-mono text-sm" />
        <Label>reject examples (по строке)</Label>
        <Textarea value={rejectText} onChange={(e) => setRejectText(e.target.value)} className="min-h-24 font-mono text-sm" />
        <Button
          size="sm"
          onClick={() => createProfile.mutate()}
          disabled={createProfile.isPending}
        >
          Создать профиль
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">v{data.profile.version}</Badge>
        {data.profile.has_draft ? (
          <Badge>есть черновик</Badge>
        ) : (
          <Badge variant="secondary">черновик пуст</Badge>
        )}
        <label className="flex items-center gap-2 text-sm ml-auto">
          <input
            type="checkbox"
            checked={requiresLlm}
            onChange={(e) => setRequiresLlm(e.target.checked)}
          />
          requires_llm
        </label>
      </div>

      <div className="space-y-1.5">
        <Label>target_lead</Label>
        <Textarea
          value={targetLead}
          onChange={(e) => setTargetLead(e.target.value)}
          className="min-h-20"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>accept examples</Label>
          <Textarea
            className="min-h-40 font-mono text-sm"
            value={acceptText}
            onChange={(e) => setAcceptText(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label>reject examples</Label>
          <Textarea
            className="min-h-40 font-mono text-sm"
            value={rejectText}
            onChange={(e) => setRejectText(e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>conflict_slugs</Label>
        <Textarea
          className="min-h-20 font-mono text-sm"
          value={conflictsText}
          onChange={(e) => setConflictsText(e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <Label>reason (обязателен для publish/rollback)</Label>
        <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="почему меняем" />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={() => saveDraft.mutate()} disabled={saveDraft.isPending}>
          Сохранить draft
        </Button>
        <Button size="sm" onClick={() => publish.mutate()} disabled={publish.isPending}>
          Опубликовать
        </Button>
        <Button size="sm" variant="destructive" onClick={() => rollback.mutate()} disabled={rollback.isPending}>
          Rollback
        </Button>
      </div>

      {diffEntries.length > 0 && (
        <div className="rounded-md border p-3 text-xs space-y-2">
          <div className="font-medium">Diff draft vs published</div>
          {diffEntries.map(([key, value]) => (
            <div key={key}>
              <span className="font-mono">{key}</span>
              <pre className="whitespace-pre-wrap text-muted-foreground mt-1">
                {JSON.stringify(value, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-2 border-t pt-4">
        <Label>Preview одного сообщения (offline markers)</Label>
        <Textarea
          value={previewText}
          onChange={(e) => setPreviewText(e.target.value)}
          placeholder="Вставьте текст сообщения…"
          className="min-h-20"
        />
        <Button
          size="sm"
          variant="outline"
          onClick={() => preview.mutate()}
          disabled={preview.isPending || !previewText.trim()}
        >
          Preview
        </Button>
        {previewResult && (
          <pre className="text-xs whitespace-pre-wrap rounded-md bg-muted p-2">{previewResult}</pre>
        )}
      </div>
    </div>
  );
}
