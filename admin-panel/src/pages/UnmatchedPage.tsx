import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, X, RefreshCw } from "lucide-react";

interface UnmatchedItem {
  ts: string;
  chat: string;
  msg_id: number;
  text: string;
}

interface UnmatchedList {
  items: UnmatchedItem[];
  total: number;
  page: number;
  per_page: number;
}

const PER_PAGE = 30;

export default function UnmatchedPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [chat, setChat] = useState("");

  const queryKey = ["unmatched", page, search, chat];
  const { data, isLoading, refetch } = useQuery<UnmatchedList>({
    queryKey,
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("per_page", String(PER_PAGE));
      if (search) params.set("search", search);
      if (chat && chat !== "all") params.set("chat", chat);
      return api(`/api/unmatched?${params.toString()}`);
    },
  });

  const { data: countData } = useQuery<{ count: number }>({
    queryKey: ["unmatched-count"],
    queryFn: () => api("/api/unmatched/count"),
    refetchInterval: 30_000,
  });

  const { data: chatsData } = useQuery<{ chats: string[] }>({
    queryKey: ["unmatched-chats"],
    queryFn: () => api("/api/unmatched/chats"),
  });

  const totalPages = Math.ceil((data?.total ?? 0) / PER_PAGE);

  const formatTime = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return iso;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            📭 Несматченные сообщения
          </h1>
          <p className="text-muted-foreground mt-1">
            Сообщения, которые не совпали ни с одним сегментом. Последние{" "}
            {countData?.count ?? "..."} из 10 000.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="size-4 mr-1" /> Обновить
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative w-72">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            placeholder="Поиск по тексту или чату..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="pl-8"
          />
        </div>

        <Select
          value={chat || "all"}
          onValueChange={(value) => { setChat(value === "all" ? "" : value); setPage(1); }}
        >
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Все чаты" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все чаты</SelectItem>
            {chatsData?.chats.map((c) => (
              <SelectItem key={c} value={c}>
                @{c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {(search || chat) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { setSearch(""); setChat(""); setPage(1); }}
          >
            <X className="size-4 mr-1" /> Сбросить
          </Button>
        )}
      </div>

      {/* Table */}
      <Card>
        <CardContent className="pt-6">
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-36">Время</TableHead>
                    <TableHead className="w-36">Чат</TableHead>
                    <TableHead className="w-20">Msg ID</TableHead>
                    <TableHead>Текст</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data?.items.map((item, i) => (
                    <TableRow key={`${item.msg_id}-${i}`}>
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                        {formatTime(item.ts)}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="font-mono text-xs">
                          @{item.chat}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {item.msg_id}
                      </TableCell>
                      <TableCell className="text-sm max-w-lg break-words">
                        {item.text}
                      </TableCell>
                    </TableRow>
                  ))}
                  {data?.items.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center text-muted-foreground py-8">
                        {search || chat
                          ? "Ничего не найдено по фильтрам"
                          : "Нет несматченных сообщений"}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between pt-4">
                  <p className="text-sm text-muted-foreground">
                    Всего: {data?.total ?? 0}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page <= 1}
                      onClick={() => setPage(page - 1)}
                    >
                      ← Назад
                    </Button>
                    <span className="flex items-center text-sm px-3">
                      {page} / {totalPages}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page >= totalPages}
                      onClick={() => setPage(page + 1)}
                    >
                      Вперёд →
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
