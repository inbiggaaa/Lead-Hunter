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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

// ── Types ──

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

interface SegmentItem extends CrudItem {
  id: number;
  slug: string;
  emoji: string;
  title_ru: string;
  title_en: string;
  sort_order: number;
  is_active: boolean;
}

interface KeywordItem {
  id: number;
  text: string;
  is_regex: boolean;
  is_active: boolean;
}

interface KeywordData {
  segment: { id: number; slug: string; title_ru: string; emoji: string };
  demand: KeywordItem[];
  stop: KeywordItem[];
  synonym: KeywordItem[];
}

// ── Generic CRUD table (for Countries & Cities) ──

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
    fields.forEach(({ key }) => { f[key] = item[key] ?? ""; });
    setForm(f);
  };

  const openCreate = () => {
    setCreating(true);
    const f: Record<string, unknown> = {};
    fields.forEach(({ key, type }) => { f[key] = type === "checkbox" ? false : ""; });
    setForm(f);
  };

  const handleSave = () => saveMutation.mutate(form);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">{title}</h3>
        <Button size="sm" onClick={openCreate}><Plus className="size-4 mr-1" /> Добавить</Button>
      </div>
      {isLoading ? (
        <div className="space-y-2"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((c) => (<TableHead key={c.key}>{c.label}</TableHead>))}
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((item) => (
              <TableRow key={item.id}>
                {columns.map((c) => (
                  <TableCell key={c.key}>
                    {c.render ? c.render(item[c.key], item) : String(item[c.key] ?? "")}
                  </TableCell>
                ))}
                <TableCell>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(item)}><Pencil className="size-3" /></Button>
                    <Button variant="ghost" size="icon" onClick={() => { if (confirm("Удалить?")) deleteMutation.mutate(item.id); }}><Trash2 className="size-3 text-destructive" /></Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Dialog open={!!editing || creating} onOpenChange={() => { setEditing(null); setCreating(false); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{editing ? "Редактировать" : "Создать"}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            {fields.map((f) => (
              <div key={f.key} className="space-y-2">
                <Label>{f.label}</Label>
                {f.type === "checkbox" ? (
                  <input type="checkbox" checked={!!form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.checked })} className="size-4" />
                ) : (
                  <Input value={String(form[f.key] ?? "")} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
                )}
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setEditing(null); setCreating(false); }}>Отмена</Button>
            <Button onClick={handleSave} disabled={saveMutation.isPending}>{saveMutation.isPending ? "Сохранение..." : "Сохранить"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Keywords sub-table (inside segment edit dialog) ──

const KW_COLORS: Record<string, string> = {
  demand: "text-green-600",
  stop: "text-red-600",
  synonym: "text-blue-600",
};

function KeywordsSection({
  segmentId,
}: {
  segmentId: number;
}) {
  const queryClient = useQueryClient();
  const [kwTab, setKwTab] = useState("demand");
  const [kwEditing, setKwEditing] = useState<KeywordItem | null>(null);
  const [kwCreating, setKwCreating] = useState(false);
  const [kwForm, setKwForm] = useState<Record<string, unknown>>({});

  const { data: kwData, isLoading: kwLoading } = useQuery<KeywordData>({
    queryKey: ["segment-keywords", segmentId],
    queryFn: () => api(`/api/segments/${segmentId}/keywords`),
  });

  const saveKwMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => {
      const isEdit = !!kwEditing;
      return api(
        `/api/segments/${segmentId}/keywords${isEdit ? `/${kwEditing!.id}` : ""}`,
        { method: isEdit ? "PUT" : "POST", body: JSON.stringify(body) },
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segment-keywords", segmentId] });
      setKwEditing(null);
      setKwCreating(false);
      toast.success(kwEditing ? "Сохранено" : "Добавлено");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteKwMutation = useMutation({
    mutationFn: (kwId: number) => api(`/api/segments/${segmentId}/keywords/${kwId}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segment-keywords", segmentId] });
      toast.success("Удалено");
    },
  });

  const openKwEdit = (item: KeywordItem, type: string) => {
    setKwEditing(item);
    setKwForm({ text: item.text, keyword_type: type, is_regex: item.is_regex, is_active: item.is_active });
  };

  const openKwCreate = (type: string) => {
    setKwCreating(true);
    setKwForm({ text: "", keyword_type: type, is_regex: false, is_active: true });
  };

  const currentKws = kwData ? (kwData as unknown as Record<string, KeywordItem[]>)[kwTab] || [] : [];
  const totalKws = kwData
    ? (kwData.demand?.length || 0) + (kwData.stop?.length || 0) + (kwData.synonym?.length || 0)
    : 0;

  return (
    <div className="space-y-3 border-t pt-4 mt-4">
      <div className="flex items-center justify-between">
        <h4 className="font-medium text-sm">Ключевые слова ({totalKws})</h4>
        <Button size="sm" variant="outline" onClick={() => openKwCreate(kwTab)}>
          <Plus className="size-3 mr-1" /> Добавить
        </Button>
      </div>

      <Tabs value={kwTab} onValueChange={setKwTab}>
        <TabsList className="h-8">
          <TabsTrigger value="demand" className="text-xs px-2 py-0.5">
            🟢 Demand ({kwData?.demand?.length ?? 0})
          </TabsTrigger>
          <TabsTrigger value="stop" className="text-xs px-2 py-0.5">
            🔴 Stop ({kwData?.stop?.length ?? 0})
          </TabsTrigger>
          <TabsTrigger value="synonym" className="text-xs px-2 py-0.5">
            🔵 Synonym ({kwData?.synonym?.length ?? 0})
          </TabsTrigger>
        </TabsList>

        <TabsContent value={kwTab} className="mt-2">
          {kwLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : currentKws.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">Нет ключевых слов этого типа</p>
          ) : (
            <div className="max-h-64 overflow-y-auto border rounded-md">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8">#</TableHead>
                    <TableHead>Текст</TableHead>
                    <TableHead className="w-16 text-center">Regex</TableHead>
                    <TableHead className="w-16 text-center">Активно</TableHead>
                    <TableHead className="w-20" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {currentKws.map((kw, i) => (
                    <TableRow key={kw.id}>
                      <TableCell className="text-xs text-muted-foreground">{i + 1}</TableCell>
                      <TableCell className={`text-sm ${KW_COLORS[kwTab] || ""}`}>
                        {kw.text}
                      </TableCell>
                      <TableCell className="text-center">
                        {kw.is_regex ? <Badge variant="default" className="text-xs">Да</Badge> : <span className="text-xs text-muted-foreground">—</span>}
                      </TableCell>
                      <TableCell className="text-center">
                        {kw.is_active ? <Badge variant="default" className="text-xs">Да</Badge> : <Badge variant="secondary" className="text-xs">Нет</Badge>}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-0.5">
                          <Button variant="ghost" size="icon" className="size-7" onClick={() => openKwEdit(kw, kwTab)}>
                            <Pencil className="size-3" />
                          </Button>
                          <Button variant="ghost" size="icon" className="size-7" onClick={() => { if (confirm("Удалить слово?")) deleteKwMutation.mutate(kw.id); }}>
                            <Trash2 className="size-3 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Keyword edit/create mini-dialog */}
      <Dialog open={!!kwEditing || kwCreating} onOpenChange={() => { setKwEditing(null); setKwCreating(false); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{kwEditing ? "Редактировать слово" : "Добавить слово"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Текст</Label>
              <Input value={String(kwForm.text ?? "")} onChange={(e) => setKwForm({ ...kwForm, text: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Тип</Label>
              <Select value={String(kwForm.keyword_type ?? "demand")} onValueChange={(v) => setKwForm({ ...kwForm, keyword_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="demand">🟢 Demand</SelectItem>
                  <SelectItem value="stop">🔴 Stop</SelectItem>
                  <SelectItem value="synonym">🔵 Synonym</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-1.5 text-sm">
                <input type="checkbox" checked={!!kwForm.is_regex} onChange={(e) => setKwForm({ ...kwForm, is_regex: e.target.checked })} className="size-3.5" />
                Regex
              </label>
              <label className="flex items-center gap-1.5 text-sm">
                <input type="checkbox" checked={!!kwForm.is_active} onChange={(e) => setKwForm({ ...kwForm, is_active: e.target.checked })} className="size-3.5" />
                Активно
              </label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => { setKwEditing(null); setKwCreating(false); }}>Отмена</Button>
            <Button size="sm" onClick={() => saveKwMutation.mutate(kwForm)} disabled={saveKwMutation.isPending}>
              {saveKwMutation.isPending ? "..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Segments tab (custom: table + wide edit dialog with keywords) ──

function SegmentsTab() {
  const [page] = useState(1);
  const [editing, setEditing] = useState<SegmentItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<CrudList>({
    queryKey: ["segments", page],
    queryFn: () => api(`/api/segments?page=${page}&per_page=50`),
  });

  const saveMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      editing
        ? api(`/api/segments/${editing.id}`, { method: "PUT", body: JSON.stringify(body) })
        : api(`/api/segments`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segments"] });
      setEditing(null);
      setCreating(false);
      toast.success(editing ? "Сохранено" : "Создано");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api(`/api/segments/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segments"] });
      toast.success("Удалено");
    },
  });

  const openEdit = (item: SegmentItem) => {
    setEditing(item);
    setForm({
      slug: item.slug, emoji: item.emoji, title_ru: item.title_ru,
      title_en: item.title_en, sort_order: item.sort_order, is_active: item.is_active,
    });
  };

  const openCreate = () => {
    setCreating(true);
    setForm({ slug: "", emoji: "", title_ru: "", title_en: "", sort_order: 0, is_active: true });
  };

  const handleSave = () => saveMutation.mutate(form);
  const isDialogOpen = !!editing || creating;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Направления</h3>
        <Button size="sm" onClick={openCreate}><Plus className="size-4 mr-1" /> Добавить</Button>
      </div>

      {isLoading ? (
        <div className="space-y-2"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead></TableHead>
              <TableHead>Slug</TableHead>
              <TableHead>RU</TableHead>
              <TableHead>EN</TableHead>
              <TableHead className="w-20">Порядок</TableHead>
              <TableHead className="w-20">Активен</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((item) => {
              const seg = item as SegmentItem;
              return (
                <TableRow key={seg.id}>
                  <TableCell className="text-lg">{seg.emoji}</TableCell>
                  <TableCell className="font-mono text-xs">{seg.slug}</TableCell>
                  <TableCell>{seg.title_ru}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">{seg.title_en}</TableCell>
                  <TableCell className="text-center">{seg.sort_order}</TableCell>
                  <TableCell>
                    {seg.is_active ? <Badge variant="default">Да</Badge> : <Badge variant="secondary">Нет</Badge>}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(seg)}><Pencil className="size-3" /></Button>
                      <Button variant="ghost" size="icon" onClick={() => { if (confirm("Удалить направление?")) deleteMutation.mutate(seg.id); }}>
                        <Trash2 className="size-3 text-destructive" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      {/* Segment edit/create dialog — wide, with keywords */}
      <Dialog open={isDialogOpen} onOpenChange={() => { setEditing(null); setCreating(false); }}>
        <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editing ? `${editing.emoji} ${editing.title_ru}` : "Новое направление"}
            </DialogTitle>
          </DialogHeader>

          {/* Segment fields */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Slug</Label>
              <Input value={String(form.slug ?? "")} onChange={(e) => setForm({ ...form, slug: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Emoji</Label>
              <Input value={String(form.emoji ?? "")} onChange={(e) => setForm({ ...form, emoji: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Название RU</Label>
              <Input value={String(form.title_ru ?? "")} onChange={(e) => setForm({ ...form, title_ru: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Название EN</Label>
              <Input value={String(form.title_en ?? "")} onChange={(e) => setForm({ ...form, title_en: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Порядок</Label>
              <Input type="number" value={String(form.sort_order ?? 0)} onChange={(e) => setForm({ ...form, sort_order: parseInt(e.target.value) || 0 })} />
            </div>
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-1.5 text-sm">
                <input type="checkbox" checked={!!form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} className="size-4" />
                Активен
              </label>
            </div>
          </div>

          {/* Keywords section (only in edit mode) */}
          {editing && <KeywordsSection segmentId={editing.id} />}

          <DialogFooter>
            <Button variant="outline" onClick={() => { setEditing(null); setCreating(false); }}>Отмена</Button>
            <Button onClick={handleSave} disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "Сохранение..." : "Сохранить направление"}
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
        </TabsList>
        <TabsContent value="segments">
          <Card>
            <CardContent className="pt-6">
              <SegmentsTab />
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
      </Tabs>
    </div>
  );
}
