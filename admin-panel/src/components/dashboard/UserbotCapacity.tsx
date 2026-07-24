import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle, Bot, Gauge } from "lucide-react";
import { api } from "@/lib/api";
import { Line } from "react-chartjs-2";

interface FleetInfo {
  configured_accounts: number;
  available_accounts: number;
  required_accounts: number;
  additional_accounts: number;
  utilization_percent: number;
  projected_daily_rpc: number;
  safe_daily_capacity: number;
  eligible_chats: number;
  parked_chats: number;
  has_deficit: boolean;
  server_now: number;
}

interface AccountInfo {
  account_id: number;
  state: string;
  power_percent: number;
  recommended_state: string;
  recommended_power_percent: number;
  rpc_1h: number;
  rpc_24h: number;
  safe_daily_budget: number;
  utilization_percent: number;
  assigned_chats: number;
  cooldown_until: number | null;
  stage_until: number | null;
  last_rpc_at: number | null;
}

interface UserbotStats {
  fleet: FleetInfo;
  accounts: AccountInfo[];
  rpc_minutes: { minute: string; account_id: number; count: number }[];
}

function formatCountdown(deadline: number | null, serverNow: number): string {
  if (!deadline) return "—";
  const left = Math.max(0, deadline - serverNow);
  const h = Math.floor(left / 3600);
  const m = Math.floor((left % 3600) / 60);
  return `${h}ч ${m}м`;
}

const STATE_LABEL: Record<string, string> = {
  NORMAL: "Норма",
  THROTTLED: "Ограничен",
  COOLDOWN: "Cooldownoldown",
  RECOVERY: "Восстановление",
  QUARANTINED: "Карантин",
  OFFLINE: "Офлайн",
};

export function UserbotCapacity() {
  const { data, isLoading, isError, error, dataUpdatedAt } = useQuery<UserbotStats>({
    queryKey: ["userbot-capacity"],
    queryFn: () => api.get("/api/stats/userbots"),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
  });

  if (isLoading && !data) {
    return <Skeleton className="h-48 w-full" />;
  }

  if (isError && !data) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-destructive">
          Данные userbot недоступны: {String((error as Error)?.message || error)}
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  const { fleet, accounts, rpc_minutes } = data;
  const byMinute = new Map<string, number>();
  for (const row of rpc_minutes) {
    byMinute.set(row.minute, (byMinute.get(row.minute) || 0) + row.count);
  }
  const labels = [...byMinute.keys()].slice(0, 60).reverse();
  const values = labels.map((k) => byMinute.get(k) || 0);
  const safePerMinute = Math.max(1, Math.floor(fleet.safe_daily_capacity / (24 * 60)));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Bot className="h-4 w-4" />
            Userbot capacity
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <div className="text-muted-foreground">Utilization / reserve</div>
            <div className="font-medium">
              {fleet.utilization_percent}% / {Math.max(0, 100 - fleet.utilization_percent)}%
            </div>
          </div>
          <div>
            <div className="text-muted-foreground">Accounts</div>
            <div className="font-medium">
              {fleet.available_accounts} / {fleet.required_accounts} (of {fleet.configured_accounts})
            </div>
          </div>
          <div>
            <div className="text-muted-foreground">Eligible / parked</div>
            <div className="font-medium">
              {fleet.eligible_chats} / {fleet.parked_chats}
            </div>
          </div>
          <div>
            <div className="text-muted-foreground">Projected RPC / day</div>
            <div className="font-medium">{fleet.projected_daily_rpc}</div>
          </div>
        </CardContent>
      </Card>

      {fleet.has_deficit && fleet.additional_accounts > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 text-destructive" aria-hidden />
          <span>
            Подключить ещё {fleet.additional_accounts} userbot-аккаунта
          </span>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {accounts.map((acc) => (
          <Card key={acc.account_id}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Gauge className="h-4 w-4" aria-hidden />
                Account #{acc.account_id}: {STATE_LABEL[acc.state] || acc.state} ({acc.state})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <div>Power: {acc.power_percent}% (rec {acc.recommended_power_percent}%)</div>
              <div>RPC 1h / 24h: {acc.rpc_1h} / {acc.rpc_24h}</div>
              <div>Budget: {acc.rpc_24h}/{acc.safe_daily_budget} ({acc.utilization_percent}%)</div>
              <div>Assigned chats: {acc.assigned_chats}</div>
              <div>
                Cooldown / stage: {formatCountdown(acc.cooldown_until, fleet.server_now)} /{" "}
                {formatCountdown(acc.stage_until, fleet.server_now)}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">RPC / minute (fleet)</CardTitle>
        </CardHeader>
        <CardContent>
          <Line
            data={{
              labels,
              datasets: [
                {
                  label: "RPC",
                  data: values,
                  borderColor: "#2563eb",
                  tension: 0.2,
                },
                {
                  label: "Safe line",
                  data: labels.map(() => safePerMinute),
                  borderColor: "#dc2626",
                  borderDash: [6, 4],
                  pointRadius: 0,
                },
              ],
            }}
            options={{
              responsive: true,
              plugins: { legend: { position: "bottom" } },
              scales: { x: { display: false } },
            }}
          />
          {isError && dataUpdatedAt > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              Показаны последние известные данные (обновление не удалось).
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
