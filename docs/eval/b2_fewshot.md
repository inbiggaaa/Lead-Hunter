# B2 — few-shot calibration in LLM system prompt

**Дата:** 20.07.2026  
**Статус кода:** внедрено в `app/userbot/llm_validator.py` (`FEW_SHOT_EXAMPLES`).  
**Живой LLM-батч / полный eval:** ждут API-ключ + прод-корпус (owner gate).

## Что сделано

- 6 вручную отобранных примеров (не автоподбор с живого фидбека):
  - 2× 👍 → DEMAND (repair, language-courses)
  - 3× 👎 → OFFER (currency-exchange, massage, design — частые FP в отчётах 10–12.07)
  - 1× 👎-паттерн → OTHER (социальный попутчик)
- Блок `CALIBRATION` добавляется в `build_system_prompt` после базовых EXAMPLES.
- Unit: `tests/test_b2_few_shot.py` (рост длины промпта ~27% ≤30%).

## Приёмка плана (осталось)

```bash
# На worker с DEEPSEEK_API_KEY — эталон ≥37/40, ошибок типа A (потеря лида) = 0
docker compose exec worker python tools/test_llm_prompt_batch.py

# Полный eval-diff после выката промпта
venv/bin/python tools/eval_matching.py > docs/eval/b2_fewshot_eval_diff.md
```

Проверить `prompt_tokens` в `llm_decisions` / логах: рост ≤30% vs pre-B2.

## Правило правок

Менять `FEW_SHOT_EXAMPLES` только вручную + с eval-diff. Не подключать live feedback
автоматически — риск дрейфа и потери лидов (asymmetry rule C2).
