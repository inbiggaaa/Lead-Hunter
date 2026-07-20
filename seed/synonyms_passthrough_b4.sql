-- B4 / phase-2: synonym (domain) dictionaries for high-traffic pass-through segments.
-- Idempotent. Apply ONLY when A1 origin-split is already live (synonym ≠ Pass1 demand).
-- Deploy window: worker stopped → alembic → up → psql -f this file → wait ≤5min reload.
--
-- Top-6 by traffic from docs/eval/reality_audit.md (12.07.2026).

INSERT INTO segment_keywords (segment_id, text, keyword_type, is_regex, is_active)
SELECT s.id, v.text, 'synonym', false, true
FROM segments s
JOIN (VALUES
  -- housing-rent
  ('housing-rent', 'квартира'),
  ('housing-rent', 'квартиру'),
  ('housing-rent', 'апартаменты'),
  ('housing-rent', 'студия'),
  ('housing-rent', 'жильё'),
  ('housing-rent', 'жилье'),
  ('housing-rent', 'комнату'),
  ('housing-rent', 'apartment'),
  -- currency-exchange
  ('currency-exchange', 'usdt'),
  ('currency-exchange', 'обмен'),
  ('currency-exchange', 'валют'),
  ('currency-exchange', 'доллар'),
  ('currency-exchange', 'vnd'),
  ('currency-exchange', 'курс'),
  -- design
  ('design', 'логотип'),
  ('design', 'дизайн'),
  ('design', 'фирменный стиль'),
  ('design', 'брендинг'),
  ('design', 'визитки'),
  -- fitness
  ('fitness', 'йога'),
  ('fitness', 'тренер'),
  ('fitness', 'фитнес'),
  ('fitness', 'зал'),
  ('fitness', 'тренировк'),
  -- repair
  ('repair', 'сантехник'),
  ('repair', 'электрик'),
  ('repair', 'ремонт'),
  ('repair', 'мастер'),
  ('repair', 'починить'),
  -- visa-support
  ('visa-support', 'виза'),
  ('visa-support', 'визу'),
  ('visa-support', 'внж'),
  ('visa-support', 'миграцион'),
  ('visa-support', 'visa')
) AS v(slug, text) ON s.slug = v.slug
ON CONFLICT (segment_id, text, keyword_type) DO NOTHING;
