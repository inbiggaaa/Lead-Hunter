import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ChevronRight,
  ChevronLeft,
  Plus,
  Pencil,
  Trash2,
  Save,
  FolderOpen,
  Layers,
  Key,
} from "lucide-react";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LlmProfileEditor } from "@/components/LlmProfileEditor";

// ── Types ──

interface Category {
  id: number;
  slug: string;
  emoji: string;
  title_ru: string;
  sort_order: number;
  is_active: boolean;
}

interface Segment {
  id: number;
  category_id?: number;
  slug: string;
  emoji: string;
  title_ru: string;
  title_en?: string;
  sort_order: number;
  is_active: boolean;
}

interface KeywordsData {
  demand: string[];
  stop: string[];
}

interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

// ── View state for 3-level drill-down ──

type ViewState =
  | { level: "categories" }
  | { level: "subcategories"; category: Category }
  | { level: "keywords"; category: Category; segment: Segment };

// ── Breadcrumb ──

function Breadcrumb({
  view,
  onBack,
}: {
  view: ViewState;
  onBack: () => void;
}) {
  return (
    <nav className="flex items-center gap-1.5 text-sm text-muted-foreground mb-1">
      <button
        onClick={() => {
          if (view.level === "keywords") onBack();
          else if (view.level === "subcategories") onBack();
        }}
        className="hover:text-foreground transition-colors flex items-center gap-1"
      >
        <Layers className="size-3.5" />
        Категории
      </button>

      {view.level !== "categories" && (
        <>
          <ChevronRight className="size-3.5" />
          <button
            onClick={() => {
              if (view.level === "keywords") onBack();
            }}
            className="hover:text-foreground transition-colors flex items-center gap-1 font-medium text-foreground"
          >
            <FolderOpen className="size-3.5" />
            {view.category.emoji} {view.category.title_ru}
          </button>
        </>
      )}

      {view.level === "keywords" && (
        <>
          <ChevronRight className="size-3.5" />
          <span className="font-medium text-foreground flex items-center gap-1">
            <Key className="size-3.5" />
            {view.segment.emoji} {view.segment.title_ru}
          </span>
        </>
      )}
    </nav>
  );
}

// ── Level 1: Categories ──

function CategoriesList({
  onSelectCategory,
}: {
  onSelectCategory: (category: Category) => void;
}) {
  const [editing, setEditing] = useState<Category | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<ListResponse<Category>>({
    queryKey: ["categories"],
    queryFn: () => api("/api/categories?page=1&per_page=200"),
  });

  const saveMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      editing
        ? api(`/api/categories/${editing.id}`, {
            method: "PUT",
            body: JSON.stringify(body),
          })
        : api("/api/categories", {
            method: "POST",
            body: JSON.stringify(body),
          }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setEditing(null);
      setCreating(false);
      toast.success(editing ? "Сохранено" : "Создано");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      api(`/api/categories/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      toast.success("Удалено");
    },
  });

  const openEdit = (item: Category) => {
    setEditing(item);
    setForm({
      slug: item.slug,
      emoji: item.emoji,
      title_ru: item.title_ru,
      sort_order: item.sort_order,
      is_active: item.is_active,
    });
  };

  const openCreate = () => {
    setCreating(true);
    setForm({
      slug: "",
      emoji: "",
      title_ru: "",
      sort_order: 0,
      is_active: true,
    });
  };

  const handleSave = () => saveMutation.mutate(form);

  const categories = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Категории</h3>
          <p className="text-sm text-muted-foreground">
            Нажмите на строку, чтобы перейти к подкатегориям
          </p>
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus className="size-4 mr-1" /> Добавить
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : categories.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4">
          Категории не найдены
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10"></TableHead>
              <TableHead>Slug</TableHead>
              <TableHead>Название</TableHead>
              <TableHead className="w-20">Порядок</TableHead>
              <TableHead className="w-20">Активна</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {categories.map((cat) => (
              <TableRow
                key={cat.id}
                className="cursor-pointer hover:bg-accent/50"
                onClick={() => onSelectCategory(cat)}
              >
                <TableCell className="text-lg">{cat.emoji}</TableCell>
                <TableCell className="font-mono text-xs">
                  {cat.slug}
                </TableCell>
                <TableCell className="font-medium">
                  {cat.title_ru}
                </TableCell>
                <TableCell className="text-center">
                  {cat.sort_order}
                </TableCell>
                <TableCell>
                  {cat.is_active ? (
                    <Badge variant="default">Да</Badge>
                  ) : (
                    <Badge variant="secondary">Нет</Badge>
                  )}
                </TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => openEdit(cat)}
                    >
                      <Pencil className="size-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm("Удалить категорию?"))
                          deleteMutation.mutate(cat.id);
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

      {/* Category create/edit dialog */}
      <Dialog
        open={!!editing || creating}
        onOpenChange={() => {
          setEditing(null);
          setCreating(false);
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {editing ? "Редактировать категорию" : "Новая категория"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Slug</Label>
              <Input
                value={String(form.slug ?? "")}
                onChange={(e) => setForm({ ...form, slug: e.target.value })}
                placeholder="cleaning"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Emoji</Label>
              <Input
                value={String(form.emoji ?? "")}
                onChange={(e) => setForm({ ...form, emoji: e.target.value })}
                placeholder="🧹"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Название RU</Label>
              <Input
                value={String(form.title_ru ?? "")}
                onChange={(e) =>
                  setForm({ ...form, title_ru: e.target.value })
                }
                placeholder="Клининг"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Порядок</Label>
              <Input
                type="number"
                value={String(form.sort_order ?? 0)}
                onChange={(e) =>
                  setForm({
                    ...form,
                    sort_order: parseInt(e.target.value) || 0,
                  })
                }
              />
            </div>
            <label className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={!!form.is_active}
                onChange={(e) =>
                  setForm({ ...form, is_active: e.target.checked })
                }
                className="size-4"
              />
              Активна
            </label>
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
            <Button
              onClick={handleSave}
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? "Сохранение..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Level 2: Subcategories ──

function SubcategoriesList({
  category,
  onBack,
  onSelectSegment,
}: {
  category: Category;
  onBack: () => void;
  onSelectSegment: (segment: Segment) => void;
}) {
  const [editing, setEditing] = useState<Segment | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const queryClient = useQueryClient();

  // Fetch all segments, filter client-side by category_id
  const { data, isLoading } = useQuery<ListResponse<Segment>>({
    queryKey: ["segments"],
    queryFn: () => api("/api/segments?page=1&per_page=500"),
  });

  const segments = (data?.items ?? []).filter(
    (s) => s.category_id === category.id,
  );

  const saveMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => {
      const payload = { ...body, category_id: category.id };
      return editing
        ? api(`/api/segments/${editing.id}`, {
            method: "PUT",
            body: JSON.stringify(payload),
          })
        : api("/api/segments", {
            method: "POST",
            body: JSON.stringify(payload),
          });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segments"] });
      setEditing(null);
      setCreating(false);
      toast.success(editing ? "Сохранено" : "Создано");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      api(`/api/segments/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segments"] });
      toast.success("Удалено");
    },
  });

  const openEdit = (item: Segment) => {
    setEditing(item);
    setForm({
      slug: item.slug,
      emoji: item.emoji,
      title_ru: item.title_ru,
      title_en: item.title_en ?? "",
      sort_order: item.sort_order,
      is_active: item.is_active,
    });
  };

  const openCreate = () => {
    setCreating(true);
    setForm({
      slug: "",
      emoji: "",
      title_ru: "",
      title_en: "",
      sort_order: 0,
      is_active: true,
    });
  };

  const handleSave = () => saveMutation.mutate(form);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 px-2"
              onClick={onBack}
            >
              <ChevronLeft className="size-4" />
            </Button>
            <h3 className="text-lg font-semibold">
              {category.emoji} {category.title_ru}
            </h3>
          </div>
          <p className="text-sm text-muted-foreground ml-10">
            Нажмите на строку, чтобы редактировать ключевые слова
          </p>
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus className="size-4 mr-1" /> Добавить
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : segments.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4">
          Нет подкатегорий в этой категории
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10"></TableHead>
              <TableHead>Slug</TableHead>
              <TableHead>RU</TableHead>
              <TableHead>EN</TableHead>
              <TableHead className="w-20">Порядок</TableHead>
              <TableHead className="w-20">Активен</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {segments.map((seg) => (
              <TableRow
                key={seg.id}
                className="cursor-pointer hover:bg-accent/50"
                onClick={() => onSelectSegment(seg)}
              >
                <TableCell className="text-lg">{seg.emoji}</TableCell>
                <TableCell className="font-mono text-xs">
                  {seg.slug}
                </TableCell>
                <TableCell className="font-medium">
                  {seg.title_ru}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {seg.title_en || "—"}
                </TableCell>
                <TableCell className="text-center">
                  {seg.sort_order}
                </TableCell>
                <TableCell>
                  {seg.is_active ? (
                    <Badge variant="default">Да</Badge>
                  ) : (
                    <Badge variant="secondary">Нет</Badge>
                  )}
                </TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => openEdit(seg)}
                    >
                      <Pencil className="size-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm("Удалить подкатегорию?"))
                          deleteMutation.mutate(seg.id);
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

      {/* Subcategory create/edit dialog */}
      <Dialog
        open={!!editing || creating}
        onOpenChange={() => {
          setEditing(null);
          setCreating(false);
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {editing
                ? "Редактировать подкатегорию"
                : "Новая подкатегория"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Slug</Label>
              <Input
                value={String(form.slug ?? "")}
                onChange={(e) => setForm({ ...form, slug: e.target.value })}
                placeholder="flat-cleaning"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Emoji</Label>
              <Input
                value={String(form.emoji ?? "")}
                onChange={(e) => setForm({ ...form, emoji: e.target.value })}
                placeholder="🏠"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Название RU</Label>
              <Input
                value={String(form.title_ru ?? "")}
                onChange={(e) =>
                  setForm({ ...form, title_ru: e.target.value })
                }
                placeholder="Уборка квартир"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Название EN</Label>
              <Input
                value={String(form.title_en ?? "")}
                onChange={(e) =>
                  setForm({ ...form, title_en: e.target.value })
                }
                placeholder="Flat Cleaning"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Порядок</Label>
              <Input
                type="number"
                value={String(form.sort_order ?? 0)}
                onChange={(e) =>
                  setForm({
                    ...form,
                    sort_order: parseInt(e.target.value) || 0,
                  })
                }
              />
            </div>
            <label className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={!!form.is_active}
                onChange={(e) =>
                  setForm({ ...form, is_active: e.target.checked })
                }
                className="size-4"
              />
              Активен
            </label>
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
            <Button
              onClick={handleSave}
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? "Сохранение..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Level 3: Keywords Editor ──

function KeywordsEditor({
  category,
  segment,
  onBack,
  hideHeader = false,
}: {
  category: Category;
  segment: Segment;
  onBack: () => void;
  hideHeader?: boolean;
}) {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<KeywordsData>({
    queryKey: ["segment-keywords", segment.id],
    queryFn: () => api(`/api/segments/${segment.id}/keywords`),
  });

  const [demandText, setDemandText] = useState("");
  const [stopText, setStopText] = useState("");
  const [initialized, setInitialized] = useState(false);

  // Seed textareas when data arrives
  if (data && !initialized) {
    setDemandText((data.demand ?? []).map((kw: any) => kw.text || kw).join("\n"));
    setStopText((data.stop ?? []).map((kw: any) => kw.text || kw).join("\n"));
    setInitialized(true);
  }

  // Reset initialized when segment changes
  const [currentSegmentId, setCurrentSegmentId] = useState(segment.id);
  if (segment.id !== currentSegmentId) {
    setCurrentSegmentId(segment.id);
    setInitialized(false);
    setDemandText("");
    setStopText("");
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      api(`/api/segments/${segment.id}/keywords-batch`, {
        method: "PUT",
        body: JSON.stringify({
          demand: demandText,
          stop: stopText,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["segment-keywords", segment.id],
      });
      toast.success("Ключевые слова сохранены");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-4">
      {!hideHeader && (
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-2"
            onClick={onBack}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <h3 className="text-lg font-semibold">
            {segment.emoji} {segment.title_ru}
          </h3>
          <Badge variant="outline" className="ml-2 text-xs">
            {category.emoji} {category.title_ru}
          </Badge>
        </div>
        <Button
          size="sm"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending || isLoading}
        >
          <Save className="size-4 mr-1" />
          {saveMutation.isPending ? "Сохранение..." : "Сохранить"}
        </Button>
      </div>
      )}
      {hideHeader && (
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || isLoading}
          >
            <Save className="size-4 mr-1" />
            {saveMutation.isPending ? "Сохранение..." : "Сохранить"}
          </Button>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Demand keywords */}
          <div className="space-y-1.5">
            <Label className="text-sm font-medium">
              Demand-слова ({demandText ? demandText.split("\n").filter(Boolean).length : 0})
            </Label>
            <Textarea
              className="min-h-64 font-mono text-sm"
              placeholder="Одно слово или фраза на строку&#10;нужен клининг&#10;требуется уборка&#10;ищу клинера"
              value={demandText}
              onChange={(e) => setDemandText(e.target.value)}
            />
          </div>

          {/* Stop keywords */}
          <div className="space-y-1.5">
            <Label className="text-sm font-medium">
              Stop-слова ({stopText ? stopText.split("\n").filter(Boolean).length : 0})
            </Label>
            <Textarea
              className="min-h-64 font-mono text-sm"
              placeholder="Одно слово или фраза на строку&#10;записывайтесь&#10;подпишитесь&#10;акция"
              value={stopText}
              onChange={(e) => setStopText(e.target.value)}
            />
          </div>
        </div>
      )}

      <div className="text-xs text-muted-foreground">
        Изменения применяются сразу после сохранения. Одно ключевое слово или
        фраза на строку.
      </div>
    </div>
  );
}

// ── Page ──

export default function CategoriesPage() {
  const [view, setView] = useState<ViewState>({ level: "categories" });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Категории и подкатегории
        </h1>
        <p className="text-muted-foreground mt-1">
          Управление каталогом: категории, подкатегории и ключевые слова
        </p>
      </div>

      <Breadcrumb
        view={view}
        onBack={() => {
          if (view.level === "subcategories") {
            setView({ level: "categories" });
          } else if (view.level === "keywords") {
            setView({
              level: "subcategories",
              category: view.category,
            });
          }
        }}
      />

      <Card>
        <CardContent className="pt-6">
          {view.level === "categories" && (
            <CategoriesList
              onSelectCategory={(category) =>
                setView({ level: "subcategories", category })
              }
            />
          )}

          {view.level === "subcategories" && (
            <SubcategoriesList
              category={view.category}
              onBack={() => setView({ level: "categories" })}
              onSelectSegment={(segment) =>
                setView({
                  level: "keywords",
                  category: view.category,
                  segment,
                })
              }
            />
          )}

          {view.level === "keywords" && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2"
                  onClick={() =>
                    setView({
                      level: "subcategories",
                      category: view.category,
                    })
                  }
                >
                  <ChevronLeft className="size-4" />
                </Button>
                <h3 className="text-lg font-semibold">
                  {view.segment.emoji} {view.segment.title_ru}
                </h3>
                <Badge variant="outline" className="ml-2 text-xs">
                  {view.category.emoji} {view.category.title_ru}
                </Badge>
              </div>
              <Tabs defaultValue="keywords">
                <TabsList>
                  <TabsTrigger value="keywords">Ключевые слова</TabsTrigger>
                  <TabsTrigger value="llm-profile">LLM-профиль</TabsTrigger>
                </TabsList>
                <TabsContent value="keywords" className="mt-4">
                  <KeywordsEditor
                    category={view.category}
                    segment={view.segment}
                    onBack={() =>
                      setView({
                        level: "subcategories",
                        category: view.category,
                      })
                    }
                    hideHeader
                  />
                </TabsContent>
                <TabsContent value="llm-profile" className="mt-4">
                  <LlmProfileEditor segment={view.segment} />
                </TabsContent>
              </Tabs>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
