import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
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
import { Search } from "lucide-react";

interface ChannelItem {
  id: number;
  chat_username: string;
  title: string | null;
  participants: number | null;
  is_verified: boolean;
  discovered_at: string | null;
}

interface ListResponse {
  items: ChannelItem[];
  total: number;
  page: number;
  per_page: number;
}

export default function ChannelsPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [verifiedFilter, setVerifiedFilter] = useState<string>("all");

  const params = new URLSearchParams({ page: String(page), per_page: "20" });
  if (search) params.set("search", search);
  if (verifiedFilter !== "all") params.set("is_verified", verifiedFilter);

  const { data, isLoading } = useQuery<ListResponse>({
    queryKey: ["channels", page, search, verifiedFilter],
    queryFn: () => api(`/api/channels?${params}`),
  });

  const totalPages = data ? Math.ceil(data.total / data.per_page) : 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Каналы</h1>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="relative flex-1 min-w-48">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                placeholder="Поиск по username или названию..."
                className="pl-8"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              />
            </div>
            <select
              className="border rounded-md px-3 py-2 text-sm bg-background"
              value={verifiedFilter}
              onChange={(e) => { setVerifiedFilter(e.target.value); setPage(1); }}
            >
              <option value="all">Все</option>
              <option value="true">Верифицированные</option>
              <option value="false">Неверифицированные</option>
            </select>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>@username</TableHead>
                    <TableHead>Название</TableHead>
                    <TableHead>Участники</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead>Обнаружен</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data?.items.map((ch) => (
                    <TableRow key={ch.id}>
                      <TableCell className="font-mono text-sm">
                        <a
                          href={`https://t.me/${ch.chat_username}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline"
                        >
                          @{ch.chat_username}
                        </a>
                      </TableCell>
                      <TableCell>{ch.title || "—"}</TableCell>
                      <TableCell>
                        {ch.participants != null
                          ? ch.participants.toLocaleString()
                          : "—"}
                      </TableCell>
                      <TableCell>
                        {ch.is_verified ? (
                          <Badge variant="default">Verified</Badge>
                        ) : (
                          <Badge variant="secondary">Unverified</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {ch.discovered_at
                          ? new Date(ch.discovered_at).toLocaleDateString()
                          : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                  {data?.items.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                        Каналы не найдены
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
