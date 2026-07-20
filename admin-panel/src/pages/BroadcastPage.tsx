import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

interface BroadcastStats {
  total: number;
  plans: Record<string, number>;
  sources: Record<string, number>;
}

interface BroadcastPreview {
  total: number;
  confirmation_token: string;
}

export default function BroadcastPage() {
  const [planFilter, setPlanFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<BroadcastPreview | null>(null);

  const { data: stats } = useQuery<BroadcastStats>({
    queryKey: ["broadcast-stats"],
    queryFn: () => api("/api/broadcast/stats"),
  });

  const previewMutation = useMutation({
    mutationFn: () =>
      api<BroadcastPreview>("/api/broadcast/preview", {
        method: "POST",
        body: JSON.stringify({ plan: planFilter, source: sourceFilter, text }),
      }),
    onSuccess: setPreview,
    onError: (e: Error) => toast.error(e.message),
  });

  const sendMutation = useMutation({
    mutationFn: () =>
      api<{ sent: number; failed: number; total: number; error?: string }>(
        "/api/broadcast/send",
        {
          method: "POST",
          body: JSON.stringify({
            plan: planFilter,
            source: sourceFilter,
            text,
            confirmation_token: preview?.confirmation_token,
          }),
        }
      ),
    onSuccess: (data) => {
      if (data.error) {
        toast.error(data.error);
      } else {
        toast.success(`Отправлено: ${data.sent} / ${data.total} (ошибок: ${data.failed})`);
        setPreview(null);
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">📨 Рассылка</h1>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Stats */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Охват</CardTitle>
          </CardHeader>
          <CardContent>
            {stats ? (
              <div className="space-y-2">
                <div className="text-3xl font-bold">{stats.total}</div>
                <p className="text-xs text-muted-foreground">Всего пользователей</p>
                <div className="flex flex-wrap gap-2 mt-3">
                  {Object.entries(stats.plans).map(([plan, count]) => (
                    <Badge key={plan} variant="secondary">
                      {plan}: {count}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : (
              <Loader2 className="size-5 animate-spin" />
            )}
          </CardContent>
        </Card>

        {/* Form */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Отправить</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-4">
              <div className="flex-1 space-y-1.5">
                <Label className="text-xs">Тариф</Label>
                <select
                  className="w-full border rounded-md px-3 py-2 text-sm bg-background"
                  value={planFilter}
                  onChange={(e) => { setPlanFilter(e.target.value); setPreview(null); }}
                >
                  <option value="all">Все</option>
                  {stats &&
                    Object.keys(stats.plans).map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                </select>
              </div>
              <div className="flex-1 space-y-1.5">
                <Label className="text-xs">Источник</Label>
                <select
                  className="w-full border rounded-md px-3 py-2 text-sm bg-background"
                  value={sourceFilter}
                  onChange={(e) => { setSourceFilter(e.target.value); setPreview(null); }}
                >
                  <option value="all">Все</option>
                  {stats &&
                    Object.keys(stats.sources).map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                </select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Текст рассылки</Label>
              <Textarea
                rows={5}
                placeholder="Введите текст сообщения..."
                value={text}
                onChange={(e) => { setText(e.target.value); setPreview(null); }}
              />
            </div>

            <Button
              className="w-full"
              disabled={!text.trim() || previewMutation.isPending}
              onClick={() => previewMutation.mutate()}
              variant="destructive"
            >
              {previewMutation.isPending ? (
                <>
                  <Loader2 className="size-4 mr-2 animate-spin" />
                  Подготовка...
                </>
              ) : (
                "📨 Предпросмотр"
              )}
            </Button>
            {preview && (
              <Button
                className="w-full"
                disabled={sendMutation.isPending}
                onClick={() => sendMutation.mutate()}
                variant="destructive"
              >
                {sendMutation.isPending ? "Отправка..." : `Подтвердить: ${preview.total}`}
              </Button>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
