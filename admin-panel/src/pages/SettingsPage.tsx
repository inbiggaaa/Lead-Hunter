import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const PLAN_INFO = [
  { plan: "Free", maxSegments: "1", maxChannels: "1", maxKeywords: "1", notifyDay: "50" },
  { plan: "Pro", maxSegments: "3", maxChannels: "15", maxKeywords: "50", notifyDay: "150" },
  { plan: "Business", maxSegments: "∞ (60)", maxChannels: "∞ (60)", maxKeywords: "∞ (60)", notifyDay: "∞" },
];

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">⚙️ Настройки</h1>

      <Card>
        <CardHeader>
          <CardTitle>Тарифные лимиты</CardTitle>
          <CardDescription>
            Лимиты задаются в <code className="text-xs bg-muted px-1 rounded">.env</code> и
            подгружаются при старте.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 font-medium">Тариф</th>
                  <th className="text-left py-2 font-medium">Направлений</th>
                  <th className="text-left py-2 font-medium">Каналов</th>
                  <th className="text-left py-2 font-medium">Ключ. слов</th>
                  <th className="text-left py-2 font-medium">Уведомлений/день</th>
                </tr>
              </thead>
              <tbody>
                {PLAN_INFO.map((p) => (
                  <tr key={p.plan} className="border-b last:border-0">
                    <td className="py-3">
                      <Badge variant={p.plan === "Business" ? "outline" : p.plan === "Pro" ? "default" : "secondary"}>
                        {p.plan}
                      </Badge>
                    </td>
                    <td className="py-3">{p.maxSegments}</td>
                    <td className="py-3">{p.maxChannels}</td>
                    <td className="py-3">{p.maxKeywords}</td>
                    <td className="py-3">{p.notifyDay}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Системная информация</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Админ-панель</span>
            <span>Next.js + shadcn/ui</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Бэкенд</span>
            <span>FastAPI + SQLAdmin</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">БД</span>
            <span>PostgreSQL 16</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Кэш</span>
            <span>Redis 7</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
