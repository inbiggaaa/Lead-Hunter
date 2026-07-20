# DLQ replay runbook

## Inspect

```bash
docker compose exec redis redis-cli LLEN dlq:notifications
docker compose exec redis redis-cli LRANGE dlq:notifications 0 4
```

## Safe replay (one message)

```bash
# Move one DLQ item back to the main queue
docker compose exec redis redis-cli RPOPLPUSH dlq:notifications queue:notifications
# Watch worker logs for delivery / re-fail
docker compose logs -f --tail=50 worker
```

## Bulk replay (owner approval required)

Only after root-cause fix (Bot API outage, temporary ban, bad payload):

```bash
N=$(docker compose exec -T redis redis-cli LLEN dlq:notifications)
echo "Replaying $N items"
for i in $(seq 1 "$N"); do
  docker compose exec -T redis redis-cli RPOPLPUSH dlq:notifications queue:notifications >/dev/null
done
```

## Do not

- Replay while FloodWait/circuit is open
- Delete DLQ without sampling payloads
- Replay Free teaser storms without checking lifecycle caps
