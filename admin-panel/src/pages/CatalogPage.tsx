import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
import { Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

interface CrudItem {
  id: number;
  [key: string]: unknown;
}

interface CrudList {
  items: CrudItem[];
  total: number;
  page: number;
  per_page: number;
}

// ── Generic CRUD table component ──

function CrudTable({
  title,
  endpoint,
  columns,
  fields,
}: {
  title: string;
  endpoint: string;
  columns: { key: string; label: string; render?: (val: unknown, row: CrudItem) => React.ReactNode }[];
  fields: { key: string; label: string; type?: "text" | "checkbox" }[];
}) {
  const [page] = useState(1);
  const [editing, setEditing] = useState<CrudItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<CrudList>({
    queryKey: [endpoint, page],
    queryFn: () => api(`/api/${endpoint}?page=${page}&per_page=50`),
  });

  const saveMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      editing
        ? api(`/api/${endpoint}/${editing.id}`, { method: "PUT", body: JSON.stringify(body) })
        : api(`/api/${endpoint}`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [endpoint] });
      setEditing(null);
      setCreating(false);
      toast.success(editing ? "Сохранено" : "Создано");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api(`/api/${endpoint}/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [endpoint] });
      toast.success("Удалено");
    },
  });

  const openEdit = (item: CrudItem) => {
    setEditing(item);
    const f: Record<string, unknown> = {};
    fields.forEach(({ key }) => {
      f[key] = item[key] ?? "";
    });
    setForm(f);
  };

  const openCreate = () => {
    setCreating(true);
    const f: Record<string, unknown> = {};
    fields.forEach(({ key, type }) => {
      f[key] = type === "checkbox" ? false : "";
    });
    setForm(f);
  };

  const handleSave = () => saveMutation.mutate(form);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">{title}</h3>
        <Button size="sm" onClick={openCreate}>
          <Plus className="size-4 mr-1" /> Добавить
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((c) => (
                <TableHead key={c.key}>{c.label}</TableHead>
              ))}
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((item) => (
              <TableRow key={item.id}>
                {columns.map((c) => (
                  <TableCell key={c.key}>
                    {c.render
                      ? c.render(item[c.key], item)
                      : String(item[c.key] ?? "")}
                  </TableCell>
                ))}
                <TableCell>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(item)}>
                      <Pencil className="size-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm("Удалить?")) deleteMutation.mutate(item.id);
                      }}
                    >
                      <Trash2 className="size-3 text-destructive" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={!!editing || creating} onOpenChange={() => { setEditing(null); setCreating(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Редактировать" : "Создать"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {fields.map((f) => (
              <div key={f.key} className="space-y-2">
                <Label>{f.label}</Label>
                {f.type === "checkbox" ? (
                  <input
                    type="checkbox"
                    checked={!!form[f.key]}
                    onChange={(e) => setForm({ ...form, [f.key]: e.target.checked })}
                    className="size-4"
                  />
                ) : (
                  <Input
                    value={String(form[f.key] ?? "")}
                    onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                  />
                )}
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setEditing(null); setCreating(false); }}>
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

// ── Catalog Page ──

export default function CatalogPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Каталог</h1>
      <Tabs defaultValue="segments">
        <TabsList>
          <TabsTrigger value="segments">Направления</TabsTrigger>
          <TabsTrigger value="countries">Страны</TabsTrigger>
          <TabsTrigger value="cities">Города</TabsTrigger>
          <TabsTrigger value="keywords">Ключевые слова</TabsTrigger>
        </TabsList>
        <TabsContent value="segments">
          <Card>
            <CardContent className="pt-6">
              <CrudTable
                title="Направления"
                endpoint="segments"
                columns={[
                  { key: "emoji", label: "" },
                  { key: "slug", label: "Slug" },
                  { key: "title_ru", label: "RU" },
                  { key: "title_en", label: "EN" },
                  { key: "sort_order", label: "Порядок" },
                  { key: "is_active", label: "Активен", render: (v) => v ? <Badge variant="default">Да</Badge> : <Badge variant="secondary">Нет</Badge> },
                ]}
                fields={[
                  { key: "slug", label: "Slug" },
                  { key: "emoji", label: "Emoji" },
                  { key: "title_ru", label: "Название RU" },
                  { key: "title_en", label: "Название EN" },
                  { key: "sort_order", label: "Порядок" },
                  { key: "is_active", label: "Активен", type: "checkbox" },
                ]}
              />
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="countries">
          <Card>
            <CardContent className="pt-6">
              <CrudTable
                title="Страны"
                endpoint="countries"
                columns={[
                  { key: "slug", label: "Slug" },
                  { key: "name_ru", label: "RU" },
                  { key: "name_en", label: "EN" },
                  { key: "is_active", label: "Активна", render: (v) => v ? <Badge variant="default">Да</Badge> : <Badge variant="secondary">Нет</Badge> },
                ]}
                fields={[
                  { key: "slug", label: "Slug" },
                  { key: "name_ru", label: "Название RU" },
                  { key: "name_en", label: "Название EN" },
                  { key: "is_active", label: "Активна", type: "checkbox" },
                ]}
              />
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="cities">
          <Card>
            <CardContent className="pt-6">
              <CrudTable
                title="Города"
                endpoint="cities"
                columns={[
                  { key: "slug", label: "Slug" },
                  { key: "name_ru", label: "RU" },
                  { key: "name_en", label: "EN" },
                  { key: "country_id", label: "Страна ID" },
                  { key: "is_active", label: "Активен", render: (v) => v ? <Badge variant="default">Да</Badge> : <Badge variant="secondary">Нет</Badge> },
                ]}
                fields={[
                  { key: "slug", label: "Slug" },
                  { key: "name_ru", label: "Название RU" },
                  { key: "name_en", label: "Название EN" },
                  { key: "country_id", label: "ID страны" },
                  { key: "is_active", label: "Активен", type: "checkbox" },
                ]}
              />
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="keywords">
          <Card>
            <CardContent className="pt-6">
              <CrudTable
                title="Ключевые слова сегментов"
                endpoint="segment-keywords"
                columns={[
                  { key: "id", label: "ID" },
                  { key: "segment_id", label: "Сегмент" },
                  { key: "text", label: "Текст" },
                  { key: "keyword_type", label: "Тип", render: (v) => {
                    const colors: Record<string, string> = { demand: "text-green-600", stop: "text-red-600", synonym: "text-blue-600" };
                    return <span className={colors[String(v)] || ""}>{String(v)}</span>;
                  }},
                  { key: "is_active", label: "Активно", render: (v) => v ? <Badge variant="default">Да</Badge> : <Badge variant="secondary">Нет</Badge> },
                ]}
                fields={[
                  { key: "text", label: "Текст" },
                  { key: "segment_id", label: "ID сегмента" },
                  { key: "keyword_type", label: "Тип (demand/stop/synonym)" },
                  { key: "is_regex", label: "Regex", type: "checkbox" },
                  { key: "is_active", label: "Активно", type: "checkbox" },
                ]}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
