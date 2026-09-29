# Приложение Г

## Листинги ключевых фрагментов

Ниже приведены сокращённые фрагменты для иллюстрации идей реализации. Полные исходные тексты находятся в репозитории проекта. Нумерация листингов локальна для приложения Г.

### Листинг Г.1 – Вероятность клетки независимого Пуассона (идея)

```python
def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)
```

### Листинг Г.2 – Смесь Пуассона и Эло (идея)

```python
poisson = poisson_1x2(lam_home, lam_away)
elo = Probabilities(*elo_1x2(home_elo, away_elo)).normalized()
return blend(poisson, elo, weight_a=0.65)
```

### Листинг Г.3 – Предварительный счёт без Эло (идея)

```python
lam_home = (home_gf + away_ga) / 2.0
lam_away = (away_gf + home_ga) / 2.0
return poisson_mode(lam_home, lam_away)  # не ceil/floor
```

### Листинг Г.4 – Ожидание Эло с домашним преимуществом (идея)

```python
exp_home = expected_score(home_rating + 80.0, away_rating)
home_rating += 20.0 * (actual_home - exp_home)
```

### Листинг Г.5 – Проверка свежести кэша (идея)

```python
TTL_SCHEDULED_HOURS = 6
TTL_FINISHED_HOURS = 24

def is_fresh(cache_key: str, ttl_hours: float) -> bool:
    fetched = fetched_at(cache_key)
    return fetched is not None and (utcnow() - fetched) < timedelta(hours=ttl_hours)
```

### Листинг Г.6 – Граница пояснения LLM (идея)

```text
Вход: JSON фактов + вероятности + предварительный счёт.
Запрещено: угадывать иной счёт, выдумывать травмы и xG.
Выход: 2–4 предложения пояснения либо отсутствие текста, если пояснение недоступно.
```

Имена модулей и полные пути см. в инженерной документации репозитория (`docs/FORECAST.md`, `docs/ARCHITECTURE.md`).
