import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus, Pencil, Trash2, Search } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

interface StopWord {
  id: number;
  segment_id: number | null;
  segment_title: string;
  text: string;
  is_regex: boolean;
  is_active: boolean;
}

interface StopWordList {
  items: StopWord[];
  total: number;
  page: number;
  per_page: number;
}

interface Segment {
  id: number;
  title_ru: string;
  emoji: string;
}

export default function StopWordsPage() {
  const [page] = useState(1);
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<StopWord | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<StopWordList>({
    queryKey: ["stop-words", page, search],
    queryFn: () =>
      api(
        `/api/stop-words?page=${page}&per_page=50${search ? `&search=${encodeURIComponent(search)}` : ""}`
      ),
  });

  // Fetch segments for the dropdown
  const { data: segmentsData } = useQuery<{ items: Segment[] }>({
    queryKey: ["segments-dropdown"],
    queryFn: () => api("/api/segments?page=1&per_page=100"),
  });
  const segments = segmentsData?.items ?? [];

  const saveMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => {
      const clean = { ...body };
      // "all" means universal (segment_id = null)
      if (clean.segment_id === "all" || clean.segment_id === "" || clean.segment_id === 0) {
        clean.segment_id = null;
      } else if (typeof clean.segment_id === "string") {
        clean.segment_id = parseInt(clean.segment_id, 10) || null;
      }
      return editing
        ? api(`/api/stop-words/${editing.id}`, {
            method: "PUT",
            body: JSON.stringify(clean),
          })
        : api(`/api/stop-words`, {
            method: "POST",
            body: JSON.stringify(clean),
          });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stop-words"] });
      setEditing(null);
      setCreating(false);
      toast.success(editing ? "Сохранено" : "Создано");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      api(`/api/stop-words/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stop-words"] });
      toast.success("Удалено");
    },
  });

  const openEdit = (item: StopWord) => {
    setEditing(item);
    setForm({
      text: item.text,
      segment_id: item.segment_id ? String(item.segment_id) : "all",
      is_regex: item.is_regex,
      is_active: item.is_active,
    });
  };

  const openCreate = () => {
    setCreating(true);
    setForm({
      text: "",
      segment_id: "all",
      is_regex: false,
      is_active: true,
    });
  };

  const handleSave = () => saveMutation.mutate(form);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">🚫 Стоп-слова</h1>
          <p className="text-muted-foreground mt-1">
            Универсальные и сегментные стоп-фразы. Сообщения с этими фразами не попадут в уведомления.
          </p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="size-4 mr-1" /> Добавить
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6 space-y-4">
          {/* Search */}
          <div className="relative max-w-sm">
            <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input
              placeholder="Поиск по тексту..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
            />
          </div>

          {/* Table */}
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Всего: {data?.total ?? 0} стоп-слов
              </p>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16">ID</TableHead>
                    <TableHead>Текст</TableHead>
                    <TableHead>Сегмент</TableHead>
                    <TableHead className="w-20">Regex</TableHead>
                    <TableHead className="w-20">Активно</TableHead>
                    <TableHead className="w-24" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data?.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="text-muted-foreground text-xs">
                        {item.id}
                      </TableCell>
                      <TableCell className="font-medium text-red-600">
                        {item.text}
                      </TableCell>
                      <TableCell>
                        {item.segment_id ? (
                          <Badge variant="outline">{item.segment_title}</Badge>
                        ) : (
                          <Badge variant="secondary">Все сегменты</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {item.is_regex ? (
                          <Badge variant="default">Да</Badge>
                        ) : (
                          <Badge variant="secondary">Нет</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {item.is_active ? (
                          <Badge variant="default">Да</Badge>
                        ) : (
                          <Badge variant="secondary">Нет</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => openEdit(item)}
                          >
                            <Pencil className="size-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                              if (confirm("Удалить стоп-слово?"))
                                deleteMutation.mutate(item.id);
                            }}
                          >
                            <Trash2 className="size-3 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {data?.items.length === 0 && (
                    <TableRow>
                      <TableCell
                        colSpan={6}
                        className="text-center text-muted-foreground py-8"
                      >
                        Стоп-слова не найдены
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>

      {/* Edit/Create Dialog */}
      <Dialog
        open={!!editing || creating}
        onOpenChange={() => {
          setEditing(null);
          setCreating(false);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editing ? "Редактировать стоп-слово" : "Добавить стоп-слово"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Текст</Label>
              <Input
                value={String(form.text ?? "")}
                onChange={(e) => setForm({ ...form, text: e.target.value })}
                placeholder="Например: записывайтесь"
              />
            </div>
            <div className="space-y-2">
              <Label>Сегмент</Label>
              <Select
                value={String(form.segment_id ?? "all")}
                onValueChange={(value) =>
                  setForm({ ...form, segment_id: value })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Выберите сегмент" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">🌍 Все сегменты</SelectItem>
                  {segments.map((seg) => (
                    <SelectItem key={seg.id} value={String(seg.id)}>
                      {seg.emoji} {seg.title_ru}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is_regex"
                  checked={!!form.is_regex}
                  onChange={(e) =>
                    setForm({ ...form, is_regex: e.target.checked })
                  }
                  className="size-4"
                />
                <Label htmlFor="is_regex">Regex</Label>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is_active"
                  checked={!!form.is_active}
                  onChange={(e) =>
                    setForm({ ...form, is_active: e.target.checked })
                  }
                  className="size-4"
                />
                <Label htmlFor="is_active">Активно</Label>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setEditing(null);
                setCreating(false);
              }}
            >
              Отмена
            </Button>
            <Button onClick={handleSave} disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "Сохранение..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
