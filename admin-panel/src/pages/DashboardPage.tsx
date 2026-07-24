import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Users, UserPlus, CreditCard, Send, Brain, Coins, Zap, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Line, Doughnut, Bar } from "react-chartjs-2";
import { UserbotCapacity } from "@/components/dashboard/UserbotCapacity";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, ArcElement, Tooltip, Legend);

interface DashboardData {
  total_users: number;
  new_today: number;
  active_subscriptions: number;
  plans: Record<string, string>;
  sent_today: number;
  new_users_30d: { date: string; count: number }[];
}

interface DeepSeekBalanceInfo {
  currency: string;
  total: string;
  granted: string;
  topped_up: string;
}

interface LLMStats {
  total_decisions: number;
  decisions_today: number;
  balance: { is_available: boolean; infos: DeepSeekBalanceInfo[] } | null;
  tokens: {
    all_time: number;
    today: number;
    this_month: number;
    prompt_all: number;
    prompt_today: number;
    completion_all: number;
    completion_today: number;
  };
  cost: {
    all_time: number;
    today: number;
    this_month: number;
    input_price_per_1m: number;
    output_price_per_1m: number;
  };
  verdicts: Record<string, number>;
  modes: Record<string, number>;
  daily_tokens: { date: string; tokens: number; decisions: number }[];
}

interface PopularStats {
  top_countries: { name: string; slug: string; users: number; subscriptions: number }[];
  top_cities: { name: string; slug: string; country: string; subscriptions: number }[];
  top_segments: { name: string; slug: string; emoji: string; users: number; subscriptions: number }[];
  top_segments_by_leads: { name: string; slug: string; emoji: string; leads: number }[];
}

const PLAN_COLORS: Record<string, string> = {
  free: "#607D8B",
  pro: "#4CAF50",
  business: "#FF9800",
};

const VERDICT_COLORS: Record<string, string> = {
  DEMAND: "#4CAF50",
  OFFER: "#F44336",
  MIXED: "#FF9800",
  OTHER: "#607D8B",
};

function fmtCost(dollars: number): string {
  if (dollars < 0.01) return "< $0.01";
  return `$${dollars.toFixed(2)}`;
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

const CURRENCY_SYMBOL: Record<string, string> = { USD: "$", CNY: "¥" };

function money(currency: string, amount: string): string {
  const sym = CURRENCY_SYMBOL[currency];
  return sym ? `${sym}${amount}` : `${amount} ${currency}`;
}

function fmtBalance(balance: LLMStats["balance"]): string {
  if (!balance || balance.infos.length === 0) return "—";
  return balance.infos.map((b) => money(b.currency, b.total)).join(" / ");
}

function balanceSubtitle(balance: LLMStats["balance"]): string {
  if (!balance || balance.infos.length === 0) return "баланс недоступен";
  const b = balance.infos[0];
  return `пополнено ${money(b.currency, b.topped_up)} · грант ${money(b.currency, b.granted)}`;
}

export default function DashboardPage() {
  const { data, isLoading } = useQuery<DashboardData>({
    queryKey: ["dashboard"],
    queryFn: () => api("/api/stats/dashboard"),
    refetchInterval: 30_000,
  });

  const { data: llm, isLoading: llmLoading } = useQuery<LLMStats>({
    queryKey: ["llm-stats"],
    queryFn: () => api("/api/stats/llm"),
    refetchInterval: 60_000,
  });

  const { data: popular, isLoading: popularLoading } = useQuery<PopularStats>({
    queryKey: ["popular-stats"],
    queryFn: () => api("/api/stats/popular"),
    refetchInterval: 120_000,
  });

  const kpis = [
    { label: "Всего пользователей", value: data?.total_users, icon: Users, color: "text-blue-600", bg: "bg-blue-50" },
    { label: "Новых сегодня", value: data?.new_today, icon: UserPlus, color: "text-green-600", bg: "bg-green-50" },
    { label: "Активных подписок", value: data?.active_subscriptions, icon: CreditCard, color: "text-orange-600", bg: "bg-orange-50" },
    { label: "Уведомлений сегодня", value: data?.sent_today, icon: Send, color: "text-purple-600", bg: "bg-purple-50" },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Дашборд</h1>

      {/* === Core KPI Cards === */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {kpis.map((kpi) => (
          <Card key={kpi.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {kpi.label}
              </CardTitle>
              <div className={`p-2 rounded-lg ${kpi.bg}`}>
                <kpi.icon className={`size-4 ${kpi.color}`} />
              </div>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <div className="text-2xl font-bold">{kpi.value ?? 0}</div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <UserbotCapacity />

      {/* === LLM Token Usage === */}
      <div>
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Brain className="size-5 text-indigo-500" />
          LLM-валидация (DeepSeek)
        </h2>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Решений сегодня</CardTitle>
              <Zap className="size-4 text-amber-500" />
            </CardHeader>
            <CardContent>
              {llmLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <div className="text-2xl font-bold">{llm?.decisions_today ?? 0}</div>
              )}
              <p className="text-xs text-muted-foreground mt-1">
                Всего: {llm?.total_decisions ?? 0}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Токенов сегодня</CardTitle>
              <Brain className="size-4 text-indigo-500" />
            </CardHeader>
            <CardContent>
              {llmLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <div className="text-2xl font-bold">{fmtTokens(llm?.tokens.today ?? 0)}</div>
              )}
              <p className="text-xs text-muted-foreground mt-1">
                prompt: {fmtTokens(llm?.tokens.prompt_today ?? 0)} · completion: {fmtTokens(llm?.tokens.completion_today ?? 0)}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Токенов за месяц</CardTitle>
              <TrendingUp className="size-4 text-teal-500" />
            </CardHeader>
            <CardContent>
              {llmLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <div className="text-2xl font-bold">{fmtTokens(llm?.tokens.this_month ?? 0)}</div>
              )}
              <p className="text-xs text-muted-foreground mt-1">
                Всего: {fmtTokens(llm?.tokens.all_time ?? 0)}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Баланс ключа DeepSeek</CardTitle>
              <Coins className="size-4 text-yellow-500" />
            </CardHeader>
            <CardContent>
              {llmLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <div className="text-2xl font-bold">{fmtBalance(llm?.balance ?? null)}</div>
              )}
              <p className="text-xs text-muted-foreground mt-1">
                {balanceSubtitle(llm?.balance ?? null)} · оценка расхода (мес): ~{fmtCost(llm?.cost.this_month ?? 0)}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* LLM charts row */}
        <div className="grid gap-4 md:grid-cols-2 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Токены по дням (30 дней)</CardTitle>
            </CardHeader>
            <CardContent>
              {llmLoading ? (
                <Skeleton className="h-48 w-full" />
              ) : llm?.daily_tokens ? (
                <Bar
                  data={{
                    labels: llm.daily_tokens.map((d) => d.date),
                    datasets: [
                      {
                        label: "Токенов",
                        data: llm.daily_tokens.map((d) => d.tokens),
                        backgroundColor: "rgba(99,102,241,0.6)",
                        borderColor: "#6366f1",
                        borderWidth: 1,
                        borderRadius: 2,
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { y: { beginAtZero: true } },
                  }}
                  height={180}
                />
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Вердикты LLM</CardTitle>
            </CardHeader>
            <CardContent className="flex justify-center">
              {llmLoading ? (
                <Skeleton className="h-48 w-48 rounded-full" />
              ) : llm?.verdicts ? (
                <div className="w-48">
                  <Doughnut
                    data={{
                      labels: Object.keys(llm.verdicts),
                      datasets: [
                        {
                          data: Object.values(llm.verdicts),
                          backgroundColor: Object.keys(llm.verdicts).map(
                            (v) => VERDICT_COLORS[v] || "#999"
                          ),
                        },
                      ],
                    }}
                    options={{ responsive: true, maintainAspectRatio: true }}
                  />
                </div>
              ) : null}
          </CardContent>
        </Card>
      </div>
    </div>

    {/* === Core Charts === */}
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Новые пользователи (30 дней)</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : data?.new_users_30d ? (
            <Line
              data={{
                labels: data.new_users_30d.map((d) => d.date),
                datasets: [
                  {
                    label: "Новых",
                    data: data.new_users_30d.map((d) => d.count),
                    borderColor: "#1976d2",
                    backgroundColor: "rgba(25,118,210,0.1)",
                    fill: true,
                    tension: 0.3,
                  },
                ],
              }}
              options={{ responsive: true, maintainAspectRatio: false }}
              height={200}
            />
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Распределение по тарифам</CardTitle>
        </CardHeader>
        <CardContent className="flex justify-center">
          {isLoading ? (
            <Skeleton className="h-64 w-64 rounded-full" />
          ) : data?.plans ? (
            <div className="w-64">
              <Doughnut
                data={{
                  labels: Object.keys(data.plans),
                  datasets: [
                    {
                      data: Object.values(data.plans),
                      backgroundColor: Object.keys(data.plans).map(
                        (p) => PLAN_COLORS[p] || "#999"
                      ),
                    },
                  ],
                }}
                options={{ responsive: true, maintainAspectRatio: true }}
              />
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>

    {/* === Popular Stats === */}
    <div>
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <TrendingUp className="size-5 text-orange-500" />
        Популярность
      </h2>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Top segments by subscriptions */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Востребованные направления</CardTitle>
          </CardHeader>
          <CardContent>
            {popularLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : popular?.top_segments ? (
              <div className="space-y-1">
                {popular.top_segments.map((seg, i) => (
                  <div key={seg.slug} className="flex items-center justify-between text-sm py-1.5 border-b last:border-0">
                    <span className="flex items-center gap-2">
                      <span className="text-muted-foreground w-5 text-right">{i + 1}.</span>
                      <span>{seg.emoji}</span>
                      <span className="font-medium">{seg.name}</span>
                    </span>
                    <span className="text-muted-foreground tabular-nums">
                      {seg.users} чел · {seg.subscriptions} подписок
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Top countries */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Популярные страны</CardTitle>
          </CardHeader>
          <CardContent>
            {popularLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : popular?.top_countries ? (
              <div className="space-y-1">
                {popular.top_countries.map((c, i) => (
                  <div key={c.slug} className="flex items-center justify-between text-sm py-1.5 border-b last:border-0">
                    <span className="flex items-center gap-2">
                      <span className="text-muted-foreground w-5 text-right">{i + 1}.</span>
                      <span className="font-medium">{c.name}</span>
                    </span>
                    <span className="text-muted-foreground tabular-nums">
                      {c.users} чел · {c.subscriptions} подписок
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Top cities */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Популярные города</CardTitle>
          </CardHeader>
          <CardContent>
            {popularLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : popular?.top_cities ? (
              <div className="space-y-1">
                {popular.top_cities.map((c, i) => (
                  <div key={c.slug} className="flex items-center justify-between text-sm py-1.5 border-b last:border-0">
                    <span className="flex items-center gap-2">
                      <span className="text-muted-foreground w-5 text-right">{i + 1}.</span>
                      <span className="font-medium">{c.name}</span>
                      <span className="text-xs text-muted-foreground">({c.country})</span>
                    </span>
                    <span className="text-muted-foreground tabular-nums">{c.subscriptions} подписок</span>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Top segments by leads delivered */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Лиды по направлениям</CardTitle>
          </CardHeader>
          <CardContent>
            {popularLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : popular?.top_segments_by_leads ? (
              popular.top_segments_by_leads.length === 0 ? (
                <p className="text-sm text-muted-foreground">Нет данных</p>
              ) : (
                <div className="space-y-1">
                  {popular.top_segments_by_leads.map((seg, i) => (
                    <div key={seg.slug} className="flex items-center justify-between text-sm py-1.5 border-b last:border-0">
                      <span className="flex items-center gap-2">
                        <span className="text-muted-foreground w-5 text-right">{i + 1}.</span>
                        <span>{seg.emoji}</span>
                        <span className="font-medium">{seg.name}</span>
                      </span>
                      <span className="text-muted-foreground tabular-nums">{seg.leads} лидов</span>
                    </div>
                  ))}
                </div>
              )
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  </div>
  );
}
