import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Pagination, PaginationContent, PaginationItem,
  PaginationNext, PaginationPrevious,
} from "@/components/ui/pagination";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreHorizontal, Search } from "lucide-react";

interface UserItem {
  id: number;
  telegram_id: number;
  username: string | null;
  language: string;
  plan: string;
  plan_activated_at: string | null;
  plan_expires_at: string | null;
  is_banned: boolean;
  is_blocked_bot: boolean;
  source: string;
  created_at: string;
}

interface ListResponse {
  items: UserItem[];
  total: number;
  page: number;
  per_page: number;
}

const PLAN_VARIANTS: Record<string, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  free: { label: "Free", variant: "secondary" },
  pro: { label: "Pro", variant: "default" },
  business: { label: "Business", variant: "outline" },
};

export default function UsersPage() {
  const [page, setPage] = useState(1);
  const [planFilter, setPlanFilter] = useState("all");
  const [search, setSearch] = useState("");
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<ListResponse>({
    queryKey: ["users", page, planFilter, search],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), per_page: "20" });
      if (planFilter !== "all") params.set("plan", planFilter);
      if (search) params.set("search", search);
      return api(`/api/users?${params}`);
    },
  });

  const totalPages = data ? Math.ceil(data.total / data.per_page) : 0;

  const banMutation = useMutation({
    mutationFn: ({ id, is_banned }: { id: number; is_banned: boolean }) =>
      api(`/api/users/${id}`, {
        method: "PUT",
        body: JSON.stringify({ is_banned }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Пользователи</h1>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="relative flex-1 min-w-48">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                placeholder="Поиск по username или ID..."
                className="pl-8"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              />
            </div>
            <Select value={planFilter} onValueChange={(v) => { setPlanFilter(v); setPage(1); }}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все тарифы</SelectItem>
                <SelectItem value="free">Free</SelectItem>
                <SelectItem value="pro">Pro</SelectItem>
                <SelectItem value="business">Business</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Username</TableHead>
                    <TableHead>Тариф</TableHead>
                    <TableHead>Источник</TableHead>
                    <TableHead>Язык</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead>Создан</TableHead>
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data?.items.map((u) => (
                    <TableRow key={u.id}>
                      <TableCell className="font-mono text-xs">{u.telegram_id}</TableCell>
                      <TableCell>{u.username || "—"}</TableCell>
                      <TableCell>
                        <Badge variant={PLAN_VARIANTS[u.plan]?.variant || "secondary"}>
                          {PLAN_VARIANTS[u.plan]?.label || u.plan}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{u.source}</TableCell>
                      <TableCell className="text-xs uppercase">{u.language}</TableCell>
                      <TableCell>
                        {u.is_banned ? (
                          <Badge variant="destructive">Banned</Badge>
                        ) : u.is_blocked_bot ? (
                          <Badge variant="secondary">Blocked bot</Badge>
                        ) : (
                          <Badge variant="outline" className="text-green-600 border-green-600">Active</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(u.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreHorizontal className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() =>
                                banMutation.mutate({ id: u.id, is_banned: !u.is_banned })
                              }
                            >
                              {u.is_banned ? "Разбанить" : "Забанить"}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                  {data?.items.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                        Пользователи не найдены
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
              {totalPages > 1 && (
                <div className="mt-4 flex justify-center">
                  <Pagination>
                    <PaginationContent>
                      <PaginationItem>
                        <PaginationPrevious
                          onClick={() => setPage((p) => Math.max(1, p - 1))}
                          className={page <= 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
                        />
                      </PaginationItem>
                      <PaginationItem>
                        <span className="px-4 text-sm text-muted-foreground">
                          {page} / {totalPages}
                        </span>
                      </PaginationItem>
                      <PaginationItem>
                        <PaginationNext
                          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                          className={page >= totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
                        />
                      </PaginationItem>
                    </PaginationContent>
                  </Pagination>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
