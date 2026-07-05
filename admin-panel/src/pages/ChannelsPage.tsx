import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Pagination, PaginationContent, PaginationItem,
  PaginationNext, PaginationPrevious,
} from "@/components/ui/pagination";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, Plus, Trash2, MapPin } from "lucide-react";
import { toast } from "sonner";

interface ChannelItem {
  id: number;
  chat_username: string;
  title: string | null;
  participants: number | null;
  is_verified: boolean;
  is_ignored: boolean;
  auto_matched_country_id: number | null;
  auto_matched_city_id: number | null;
  discovered_at: string | null;
}

interface ListResponse {
  items: ChannelItem[];
  total: number;
  page: number;
  per_page: number;
}

interface Country {
  id: number;
  name_ru: string;
  slug: string;
}

interface City {
  id: number;
  name_ru: string;
  slug: string;
  country_id: number;
}

export default function ChannelsPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [verifiedFilter, setVerifiedFilter] = useState<string>("all");
  const [hasCity, setHasCity] = useState<string>("all");
  const [ignoredFilter, setIgnoredFilter] = useState<string>("false");
  const [editingChannel, setEditingChannel] = useState<number | null>(null);
  const [selectedCountry, setSelectedCountry] = useState<number | null>(null);
  const [selectedCities, setSelectedCities] = useState<number[]>([]);
  const [newCitySlug, setNewCitySlug] = useState("");
  const [newCityName, setNewCityName] = useState("");

  const params = new URLSearchParams({ page: String(page), per_page: "20" });
  if (search) params.set("search", search);
  if (verifiedFilter !== "all") params.set("is_verified", verifiedFilter);
  if (hasCity !== "all") params.set("has_city", hasCity);
  if (ignoredFilter !== "all") params.set("is_ignored", ignoredFilter);

  const { data, isLoading } = useQuery<ListResponse>({
    queryKey: ["channels", page, search, verifiedFilter, hasCity, ignoredFilter],
    queryFn: () => api(`/api/channels?${params}`),
  });

  const { data: countriesData } = useQuery<{ items: Country[] }>({
    queryKey: ["countries"],
    queryFn: () => api("/api/countries?per_page=200"),
    staleTime: 300_000,
  });

  const { data: citiesData } = useQuery<{ items: City[] }>({
    queryKey: ["cities", selectedCountry],
    queryFn: () => {
      const cp = new URLSearchParams({ per_page: "500" });
      return api(`/api/cities?${cp}`);
    },
    staleTime: 300_000,
    enabled: true,
  });

  const countries = countriesData?.items || [];
  const cities = citiesData?.items || [];
  const filteredCities = selectedCountry
    ? cities.filter((c) => c.country_id === selectedCountry)
    : cities;

  const totalPages = data ? Math.ceil(data.total / data.per_page) : 0;

  const handleBind = async (channelId: number) => {
    try {
      await api(`/api/channels/${channelId}`, {
        method: "PUT",
        body: JSON.stringify({ cities: selectedCities, country_id: selectedCountry }),
      });
      toast.success("Города привязаны");
      setEditingChannel(null);
      queryClient.invalidateQueries({ queryKey: ["channels"] });
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleIgnore = async (channelId: number) => {
    try {
      await api(`/api/channels/${channelId}`, {
        method: "PUT",
        body: JSON.stringify({ is_ignored: true }),
      });
      toast.success("Канал удалён из очереди");
      queryClient.invalidateQueries({ queryKey: ["channels"] });
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleUnignore = async (channelId: number) => {
    try {
      await api(`/api/channels/${channelId}`, {
        method: "PUT",
        body: JSON.stringify({ is_ignored: false }),
      });
      toast.success("Канал восстановлен");
      queryClient.invalidateQueries({ queryKey: ["channels"] });
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleAddCity = async () => {
    if (!newCitySlug || !newCityName || !selectedCountry) {
      toast.error("Укажите slug, название и страну");
      return;
    }
    try {
      await api("/api/cities", {
        method: "POST",
        body: JSON.stringify({
          slug: newCitySlug,
          name_ru: newCityName,
          country_id: selectedCountry,
        }),
      });
      toast.success(`Город ${newCityName} добавлен`);
      setNewCitySlug("");
      setNewCityName("");
      queryClient.invalidateQueries({ queryKey: ["cities"] });
    } catch (e) {
      toast.error(String(e));
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Каналы</h1>

      <div className="bg-amber-50 border border-amber-200 rounded-md px-4 py-2 text-sm text-amber-800">
        ⏱ Изменения (привязка города, удаление) применятся в течение часа — каналы обновляются на часовом ребилде прослушки.
      </div>

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
            <select
              className="border rounded-md px-3 py-2 text-sm bg-background"
              value={hasCity}
              onChange={(e) => { setHasCity(e.target.value); setPage(1); }}
            >
              <option value="all">Город: все</option>
              <option value="false">Без города</option>
              <option value="true">С городом</option>
            </select>
            <select
              className="border rounded-md px-3 py-2 text-sm bg-background"
              value={ignoredFilter}
              onChange={(e) => { setIgnoredFilter(e.target.value); setPage(1); }}
            >
              <option value="false">Активные</option>
              <option value="true">Игнорированные</option>
              <option value="all">Все</option>
            </select>
            <span className="text-sm text-muted-foreground">
              {data ? `Найдено: ${data.total}` : "—"}
            </span>
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
                    <TableHead>Игнор</TableHead>
                    <TableHead>Действия</TableHead>
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
                      <TableCell className="max-w-48 truncate">{ch.title || "—"}</TableCell>
                      <TableCell>
                        {ch.participants != null
                          ? ch.participants.toLocaleString()
                          : "—"}
                      </TableCell>
                      <TableCell>
                        {ch.is_ignored ? (
                          <Badge variant="destructive">Удалён</Badge>
                        ) : (
                          <Badge variant="outline">Активен</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {editingChannel === ch.id ? (
                          <div className="flex items-center gap-2 flex-wrap">
                            <select
                              className="border rounded px-2 py-1 text-xs"
                              value={selectedCountry || ""}
                              onChange={(e) => {
                                setSelectedCountry(e.target.value ? Number(e.target.value) : null);
                                setSelectedCities([]);
                              }}
                            >
                              <option value="">Страна...</option>
                              {countries.map((c) => (
                                <option key={c.id} value={c.id}>{c.name_ru}</option>
                              ))}
                            </select>
                            <select
                              multiple
                              className="border rounded px-2 py-1 text-xs min-w-[120px]"
                              value={selectedCities.map(String)}
                              onChange={(e) =>
                                setSelectedCities(
                                  Array.from(e.target.selectedOptions, (o) => Number(o.value))
                                )
                              }
                            >
                              {filteredCities.map((c) => (
                                <option key={c.id} value={c.id}>{c.name_ru}</option>
                              ))}
                            </select>
                            <Button size="sm" variant="default" onClick={() => handleBind(ch.id)}>
                              <MapPin className="size-3 mr-1" /> Привязать
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setEditingChannel(null)}>
                              Отмена
                            </Button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1">
                            {ch.auto_matched_city_id == null ? (
                              <Button size="sm" variant="outline" onClick={() => setEditingChannel(ch.id)}>
                                <MapPin className="size-3 mr-1" /> Город
                              </Button>
                            ) : (
                              <Button size="sm" variant="outline" disabled title="Редактирование привязок — отдельной задачей">
                                <MapPin className="size-3 mr-1" /> Город
                              </Button>
                            )}
                            {ch.is_ignored ? (
                              <Button size="sm" variant="outline" onClick={() => handleUnignore(ch.id)}>
                                Восстановить
                              </Button>
                            ) : (
                              <Button size="sm" variant="ghost" onClick={() => handleIgnore(ch.id)}>
                                <Trash2 className="size-3" />
                              </Button>
                            )}
                          </div>
                        )}
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

              {/* Add city row */}
              <div className="mt-4 flex items-center gap-2 p-3 border rounded-md bg-muted/30">
                <span className="text-sm font-medium">+ Город:</span>
                <select
                  className="border rounded px-2 py-1 text-xs"
                  value={selectedCountry || ""}
                  onChange={(e) => setSelectedCountry(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">Страна...</option>
                  {countries.map((c) => (
                    <option key={c.id} value={c.id}>{c.name_ru}</option>
                  ))}
                </select>
                <Input
                  placeholder="slug (напр. kashkajsh)"
                  className="w-32 text-xs h-8"
                  value={newCitySlug}
                  onChange={(e) => setNewCitySlug(e.target.value)}
                />
                <Input
                  placeholder="Название (напр. Кашкайш)"
                  className="w-40 text-xs h-8"
                  value={newCityName}
                  onChange={(e) => setNewCityName(e.target.value)}
                />
                <Button size="sm" variant="outline" onClick={handleAddCity}>
                  <Plus className="size-3 mr-1" /> Добавить
                </Button>
              </div>

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
