import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";

interface Summary {
  batch: string;
  delivered: number;
  rated: number;
  defined: number;
  correct: number;
  error: number;
  uncertain: number;
  precision: number | null;
  missing_snapshot: number;
  reasons: Record<string, number>;
  per_segment: Record<string, { correct: number; error: number; uncertain: number; precision: number | null }>;
  confusion: Array<{ delivered: string; expected: string; count: number }>;
}

interface FeedbackItem {
  chat_username: string;
  message_id: number;
  message_text_masked: string | null;
  verdict: string | null;
  reason_code: string | null;
  delivered_segments: string[];
  confirmed_segments: string[];
  expected_segment_slug: string | null;
}

function pct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export default function MatchingFeedbackPage() {
  const [batch, setBatch] = useState("ru_matching_v1");
  const [activeBatch, setActiveBatch] = useState("ru_matching_v1");

  const summaryQuery = useQuery<Summary>({
    queryKey: ["matching-feedback-summary", activeBatch],
    queryFn: () => api(`/api/matching-feedback/summary?batch=${encodeURIComponent(activeBatch)}`),
  });

  const itemsQuery = useQuery<{ items: FeedbackItem[]; count: number }>({
    queryKey: ["matching-feedback-items", activeBatch],
    queryFn: () => api(`/api/matching-feedback/items?batch=${encodeURIComponent(activeBatch)}`),
  });

  const reasonRows = useMemo(
    () => Object.entries(summaryQuery.data?.reasons ?? {}).sort((a, b) => b[1] - a[1]),
    [summaryQuery.data],
  );

  const segmentRows = useMemo(
    () => Object.entries(summaryQuery.data?.per_segment ?? {}).sort((a, b) => a[0].localeCompare(b[0])),
    [summaryQuery.data],
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label className="text-sm text-muted-foreground">Batch</label>
          <Input
            value={batch}
            onChange={(e) => setBatch(e.target.value)}
            placeholder="ru_matching_v1"
            className="w-64"
          />
        </div>
        <Button onClick={() => setActiveBatch(batch.trim() || "ru_matching_v1")}>
          Загрузить
        </Button>
        <Button variant="outline" asChild>
          <a href={`/api/matching-feedback/export.csv?batch=${encodeURIComponent(activeBatch)}`}>
            CSV
          </a>
        </Button>
        <Button variant="outline" asChild>
          <a href={`/api/matching-feedback/export.jsonl?batch=${encodeURIComponent(activeBatch)}`}>
            JSONL
          </a>
        </Button>
      </div>

      {summaryQuery.isLoading ? (
        <Skeleton className="h-28 w-full" />
      ) : summaryQuery.isError ? (
        <p className="text-destructive">Не удалось загрузить summary</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-5">
          <Kpi title="Delivered" value={String(summaryQuery.data?.delivered ?? 0)} />
          <Kpi title="Rated" value={String(summaryQuery.data?.rated ?? 0)} />
          <Kpi title="Precision" value={pct(summaryQuery.data?.precision)} />
          <Kpi title="Uncertain" value={String(summaryQuery.data?.uncertain ?? 0)} />
          <Kpi title="Missing snapshot" value={String(summaryQuery.data?.missing_snapshot ?? 0)} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Причины ошибок</CardTitle>
          </CardHeader>
          <CardContent>
            <SimpleTable
              headers={["Reason", "Count"]}
              rows={reasonRows.map(([reason, count]) => [reason, String(count)])}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Confusion matrix</CardTitle>
          </CardHeader>
          <CardContent>
            <SimpleTable
              headers={["Delivered", "Expected", "Count"]}
              rows={(summaryQuery.data?.confusion ?? []).map((c) => [
                c.delivered,
                c.expected,
                String(c.count),
              ])}
            />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Per-segment precision</CardTitle>
        </CardHeader>
        <CardContent>
          <SimpleTable
            headers={["Segment", "Correct", "Error", "Uncertain", "Precision"]}
            rows={segmentRows.map(([slug, stats]) => [
              slug,
              String(stats.correct),
              String(stats.error),
              String(stats.uncertain),
              pct(stats.precision),
            ])}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Masked examples</CardTitle>
        </CardHeader>
        <CardContent>
          {itemsQuery.isLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Chat</TableHead>
                  <TableHead>Verdict</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Masked text</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(itemsQuery.data?.items ?? []).slice(0, 50).map((item) => (
                  <TableRow key={`${item.chat_username}:${item.message_id}`}>
                    <TableCell>@{item.chat_username}</TableCell>
                    <TableCell>{item.verdict ?? "unrated"}</TableCell>
                    <TableCell>{item.reason_code ?? "—"}</TableCell>
                    <TableCell className="max-w-xl truncate">
                      {item.message_text_masked ?? "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Kpi({ title, value }: { title: string; value: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent className="text-2xl font-semibold">{value}</CardContent>
    </Card>
  );
}

function SimpleTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: string[][];
}) {
  if (!rows.length) {
    return <p className="text-sm text-muted-foreground">Нет данных</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {headers.map((h) => (
            <TableHead key={h}>{h}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, idx) => (
          <TableRow key={`${row[0]}-${idx}`}>
            {row.map((cell, cellIdx) => (
              <TableCell key={`${idx}-${cellIdx}`}>{cell}</TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
