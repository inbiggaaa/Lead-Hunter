import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Users, UserPlus, CreditCard, Send } from "lucide-react";
import { api } from "@/lib/api";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Line, Doughnut } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, ArcElement, Tooltip, Legend);

interface DashboardData {
  total_users: number;
  new_today: number;
  active_subscriptions: number;
  plans: Record<string, number>;
  sent_today: number;
  new_users_30d: { date: string; count: number }[];
}

const PLAN_COLORS: Record<string, string> = {
  free: "#607D8B",
  pro: "#4CAF50",
  business: "#FF9800",
};

export default function DashboardPage() {
  const { data, isLoading } = useQuery<DashboardData>({
    queryKey: ["dashboard"],
    queryFn: () => api("/api/stats/dashboard"),
    refetchInterval: 30_000,
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

      {/* KPI Cards */}
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

      {/* Charts */}
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
    </div>
  );
}
