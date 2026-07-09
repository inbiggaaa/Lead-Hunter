import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Pencil, Trash2, Plus } from "lucide-react";

interface Country {
  id: number;
  slug: string;
  name_ru: string | null;
  name_en: string | null;
  is_active: boolean;
}

interface City {
  id: number;
  slug: string;
  name_ru: string | null;
  name_en: string | null;
  country_id: number;
  is_active: boolean;
}

type EditRecord = Record<string, string | boolean | number>;

function CrudDialog({
  open,
  onOpenChange,
  title,
  record,
  onSave,
  fields,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  record: EditRecord;
  onSave: (data: EditRecord) => void;
  fields: { key: string; label: string; type?: "text" | "checkbox" }[];
}) {
  const [form, setForm] = useState<EditRecord>({ ...record });

  const handleSave = () => {
    onSave(form);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onOpenChange(false); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {fields.map((f) => (
            <div key={f.key} className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor={`field-${f.key}`} className="text-right">
                {f.label}
              </Label>
              {f.type === "checkbox" ? (
                <input
                  id={`field-${f.key}`}
                  type="checkbox"
                  checked={!!form[f.key]}
                  onChange={(e) =>
                    setForm({ ...form, [f.key]: e.target.checked })
                  }
                  className="h-4 w-4"
                />
              ) : (
                <Input
                  id={`field-${f.key}`}
                  value={String(form[f.key] ?? "")}
                  onChange={(e) =>
                    setForm({ ...form, [f.key]: e.target.value })
                  }
                  className="col-span-3"
                />
              )}
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button onClick={handleSave}>Сохранить</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function GeoPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState("countries");

  // ── Countries ──
  const { data: countriesData, isLoading: countriesLoading } = useQuery({
    queryKey: ["admin-countries"],
    queryFn: async () => {
      const res = await api.get("/api/countries?per_page=200");
      return (res.items ?? []) as Country[];
    },
  });

  const [countryDialog, setCountryDialog] = useState(false);
  const [editCountry, setEditCountry] = useState<EditRecord>({});

  const countryMutation = useMutation({
    mutationFn: async (data: EditRecord) => {
      if (data.id) {
        await api.put(`/api/countries/${data.id}`, data);
      } else {
        await api.post("/api/countries", data);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-countries"] });
      toast.success("Страна сохранена");
    },
    onError: () => toast.error("Ошибка сохранения"),
  });

  const deleteCountry = useMutation({
    mutationFn: (id: number) => api.delete(`/api/countries/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-countries"] });
      toast.success("Страна удалена");
    },
    onError: () => toast.error("Ошибка удаления"),
  });

  // ── Cities ──
  const { data: citiesData, isLoading: citiesLoading } = useQuery({
    queryKey: ["admin-cities"],
    queryFn: async () => {
      const res = await api.get("/api/cities?per_page=500");
      return (res.items ?? []) as City[];
    },
  });

  const [cityDialog, setCityDialog] = useState(false);
  const [editCity, setEditCity] = useState<EditRecord>({});

  const cityMutation = useMutation({
    mutationFn: async (data: EditRecord) => {
      if (data.id) {
        await api.put(`/api/cities/${data.id}`, data);
      } else {
        await api.post("/api/cities", data);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-cities"] });
      toast.success("Город сохранён");
    },
    onError: () => toast.error("Ошибка сохранения"),
  });

  const deleteCity = useMutation({
    mutationFn: (id: number) => api.delete(`/api/cities/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-cities"] });
      toast.success("Город удалён");
    },
    onError: () => toast.error("Ошибка удаления"),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Geo</h1>
        <p className="text-muted-foreground">Управление странами и городами</p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="countries">Страны</TabsTrigger>
          <TabsTrigger value="cities">Города</TabsTrigger>
        </TabsList>

        {/* ── Countries Tab ── */}
        <TabsContent value="countries" className="space-y-4">
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={() => {
                setEditCountry({ slug: "", name_ru: "", name_en: "", is_active: true });
                setCountryDialog(true);
              }}
            >
              <Plus className="w-4 h-4 mr-1" /> Страна
            </Button>
          </div>

          {countriesLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Slug</TableHead>
                  <TableHead>Название (RU)</TableHead>
                  <TableHead>Название (EN)</TableHead>
                  <TableHead>Активна</TableHead>
                  <TableHead className="w-24">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(countriesData ?? []).map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>{c.id}</TableCell>
                    <TableCell className="font-mono text-sm">{c.slug}</TableCell>
                    <TableCell>{c.name_ru}</TableCell>
                    <TableCell className="text-muted-foreground">{c.name_en}</TableCell>
                    <TableCell>
                      <Badge variant={c.is_active ? "default" : "secondary"}>
                        {c.is_active ? "Да" : "Нет"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => {
                            setEditCountry({
                              id: c.id,
                              slug: c.slug,
                              name_ru: c.name_ru ?? "",
                              name_en: c.name_en ?? "",
                              is_active: c.is_active,
                            });
                            setCountryDialog(true);
                          }}
                        >
                          <Pencil className="w-4 h-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => {
                            if (confirm(`Удалить страну ${c.name_ru}?`)) {
                              deleteCountry.mutate(c.id);
                            }
                          }}
                        >
                          <Trash2 className="w-4 h-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>

        {/* ── Cities Tab ── */}
        <TabsContent value="cities" className="space-y-4">
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={() => {
                setEditCity({
                  slug: "",
                  name_ru: "",
                  name_en: "",
                  country_id: "",
                  is_active: true,
                });
                setCityDialog(true);
              }}
            >
              <Plus className="w-4 h-4 mr-1" /> Город
            </Button>
          </div>

          {citiesLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Slug</TableHead>
                  <TableHead>Название (RU)</TableHead>
                  <TableHead>Название (EN)</TableHead>
                  <TableHead>Страна ID</TableHead>
                  <TableHead>Активен</TableHead>
                  <TableHead className="w-24">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(citiesData ?? []).map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>{c.id}</TableCell>
                    <TableCell className="font-mono text-sm">{c.slug}</TableCell>
                    <TableCell>{c.name_ru}</TableCell>
                    <TableCell className="text-muted-foreground">{c.name_en}</TableCell>
                    <TableCell>{c.country_id}</TableCell>
                    <TableCell>
                      <Badge variant={c.is_active ? "default" : "secondary"}>
                        {c.is_active ? "Да" : "Нет"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => {
                            setEditCity({
                              id: c.id,
                              slug: c.slug,
                              name_ru: c.name_ru ?? "",
                              name_en: c.name_en ?? "",
                              country_id: c.country_id,
                              is_active: c.is_active,
                            });
                            setCityDialog(true);
                          }}
                        >
                          <Pencil className="w-4 h-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => {
                            if (confirm(`Удалить город ${c.name_ru}?`)) {
                              deleteCity.mutate(c.id);
                            }
                          }}
                        >
                          <Trash2 className="w-4 h-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>
      </Tabs>

      {/* Country Dialog */}
      <CrudDialog
        open={countryDialog}
        onOpenChange={setCountryDialog}
        title={editCountry.id ? "Редактировать страну" : "Новая страна"}
        record={editCountry}
        onSave={countryMutation.mutate}
        fields={[
          { key: "slug", label: "Slug" },
          { key: "name_ru", label: "RU" },
          { key: "name_en", label: "EN" },
          { key: "is_active", label: "Активна", type: "checkbox" },
        ]}
      />

      {/* City Dialog */}
      <CrudDialog
        open={cityDialog}
        onOpenChange={setCityDialog}
        title={editCity.id ? "Редактировать город" : "Новый город"}
        record={editCity}
        onSave={cityMutation.mutate}
        fields={[
          { key: "slug", label: "Slug" },
          { key: "name_ru", label: "RU" },
          { key: "name_en", label: "EN" },
          { key: "country_id", label: "Страна ID" },
          { key: "is_active", label: "Активен", type: "checkbox" },
        ]}
      />
    </div>
  );
}
