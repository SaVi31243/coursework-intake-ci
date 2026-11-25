# Приймання робіт із підтвердженням

Сервіс приймає POST /submissions з полями `group_code` та `submission_key`. Приклад коду — SE-64. SQLite утримує один запис на ключ. Новий POST дає 201, повтор того самого ключа для тієї самої групи — 200 з початковим номером. GET /submissions/<id> читає подання. Дані у всіх серіях синтетичні.

У v1.3.0 HTTP 201 містить номер подання. У v2.3.0 після коміту формується код ACK. Прапорець `CONFIRMATION_ENABLED=0` імітує недоступність підтвердження та повертає HTTP 503 разом із номером. Окремий маршрут /health у цьому сценарії повертає 200.

## Перевірки перед пакуванням

Потрібні Python 3.12+, Docker, Docker Compose і curl. Випуски зібрано для Linux ARM64.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python lab.py test --timeout 45
```

У CI крок **Run bounded API tests** запускає pytest через subprocess. Bash із pipefail повертає помилку тестів, навіть якщо вивід передали до tee. Коли тест /health навмисно очікує HTTP 429, крок **Build the intake image** пропускається. Успішне пакування запускає окреме завдання, яке звіряє SHA-256 і прикріплює архіви до GitHub Releases.

- [Випуск v1.3.0](https://github.com/SaVi31243/coursework-intake-ci/actions/runs/45616824532)
- [Випуск v2.3.0](https://github.com/SaVi31243/coursework-intake-ci/actions/runs/45616873392)
- [Діагностика контрольного падіння](https://github.com/SaVi31243/coursework-intake-ci/actions/runs/45616880701/job/139214445308)

## Початкове приймання в Docker

Команди завантаження потрібні для чистої копії. Якщо папки `local-artifacts/v1` і `local-artifacts/v2` вже містять образи, переходь до циклу. Скрипт доставки перевіряє SHA-256 архіву та ID образу.

```bash
gh release download v1.3.0 -D local-artifacts/v1
gh release download v2.3.0 -D local-artifacts/v2

for version in v1 v2; do
  bash scripts/deliver.sh "local-artifacts/$version" staging
  container=$(docker compose -p intake-stage ps -q stage)
  python -m pytest -q --hosts="docker://$container" infra
  key="smoke-$version-$(date +%s)"
  curl -fsSi --max-time 4 -H 'Content-Type: application/json' \
    -d "{\"group_code\":\"SE-64\",\"submission_key\":\"$key\"}" \
    http://127.0.0.1:8491/submissions
done
```

Сценарій приймання використовує власний том. Обидва POST мають дати 201, а v2 має додати `confirmation`. Робочі контейнери мають спільний том SQLite, тож повернення на v1 зберігає подані роботи.

## Три серії та критерії рішення

Оператор оцінює серію з 200 новими ключами. Потрібні щонайменше 20 спроб на v2, частка помилок до 5% та p95 до 220 мс. Помилкою вважається відповідь 5xx або відсутня відповідь. p95 обчислюється серед завершених відповідей. SLI вимірює частку всіх спроб з 201 до 1 с, навчальний SLO становить 99%. Клієнт має тайм-аут 2 с та паузу 30 мс. У змішаній серії кожна десята спроба надходить до v2.

```bash
prefix="intake-$(date +%s)"
out="results/$prefix"
bash scripts/deliver.sh local-artifacts/v1 working
docker compose -p intake-work up -d prometheus
python scripts/traffic.py baseline --prefix "$prefix" --output "$out"
LAB_CONFIRMATION_ENABLED=0 bash scripts/deliver.sh local-artifacts/v2 working
python scripts/traffic.py canary --prefix "$prefix" --output "$out" &
traffic=$!
sleep 2
docker stats --no-stream $(docker compose -p intake-work ps -q v1 v2)
wait "$traffic"
sleep 2
python scripts/metrics.py --output "$out/canary-prometheus.json"
```

За перевищення ліміту оператор залишає запити на v1 і зупиняє v2. Далі виконується третя серія.

```bash
docker compose -p intake-work stop v2
python scripts/traffic.py rollback --prefix "$prefix" --output "$out"
docker compose -p intake-work logs --no-log-prefix v1 v2 | awk '/^[{]/' > "$out/submissions.jsonl"
python lab.py summarize "$out/submissions.jsonl"
python lab.py summarize "$out/absent.jsonl"
```

У canary.csv знайди рядок v2 зі статусом 503. За request_id знайди три події у журналі. Лічильник CLI враховує лише `submission_response`. Підстав номер та ключ з CSV у GET і POST на v1. Для збереженого експерименту це №310 та `intake-2511-canary-110`.

```bash
curl -fsSi --max-time 4 http://127.0.0.1:8481/submissions/310
curl -fsSi --max-time 4 -H 'Content-Type: application/json' \
  -d '{"group_code":"SE-64","submission_key":"intake-2511-canary-110"}' \
  http://127.0.0.1:8481/submissions
docker compose -p intake-work --profile working down
docker compose -p intake-stage --profile staging down
```

Замір з трьох серій та пов’язані журнали доступні у [evidence](evidence/). Під час вимкнення контейнерів томи залишаються на машині.

## Підготовка матеріалів

ШІ використано для чернеток сервісу, тестів та структури звіту. Реалізацію перевірено на двох образах із CI, а фактичні числа отримано з HTTP-запитів і Prometheus.
