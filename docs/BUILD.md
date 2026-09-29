# Сборка приложения под все платформы

Приложение собирается командой `flet build` (Flet 0.80.5, Flutter 3.38.7). Одна кодовая база → macOS, Windows, Linux, Android (APK/AAB), iOS (IPA) и web.

> Прогноз статистический. Это не совет ставить деньги.

## 1. Что уже настроено в проекте

| Что | Где | Значение |
|---|---|---|
| Название в окне и в лаунчере | `[tool.flet].product` | `Football Prognoz` |
| Организация / bundle id | `[tool.flet].org`, `bundle_id` | `com.npawcompany` / `com.npawcompany.footballprognoz` |
| Версия | `[project].version`, `[tool.flet].build_number` | `0.1.0`, `1` (увеличивайте `build_number` на каждый релиз в сторы) |
| Точка входа | `[tool.flet.app]` `path = "src"`, `module = "main"` | `src/main.py` → `football_prognoz.main.run()` |
| Зависимости в сборке | `[project].dependencies` | только runtime: `flet`, `httpx`, `pydantic-settings`, `python-dotenv` (pandas / scikit-learn — в extra `train`, в приложение не попадают) |
| Ассеты | `src/assets/` | гербы, флаги, иконки, `bg_pattern.png` (фон) |
| Иконка | `src/assets/icon.png` 1024×1024 | мяч + растущий график, непрозрачная (web, Windows, Linux, iOS) |
| Иконка macOS | `src/assets/icon_macos.png` | скруглённая плитка на прозрачном холсте |
| Иконка Android (adaptive foreground) | `src/assets/icon_android.png` + `[tool.flet.android].adaptive_icon_background = "#0C1E3D"` | логотип в безопасной зоне ~56 % |
| Заставка (splash) Android / iOS / web | `src/assets/splash.png`, `[tool.flet.splash]` | фон `#0C1E3D` (светлая и тёмная тема) |
| Разрешения Android | `[tool.flet.android.permission]` | `android.permission.INTERNET` |
| Entitlements macOS (sandbox) | `[tool.flet.macos.entitlement]` | `network.client` (HTTPS), `files.user-selected.read-write` (сохранение CSV) |
| PWA-цвета web | `[tool.flet.web]` | фон `#0C1E3D`, тема `#22C55E` |
| Папка данных | `config.resolve_app_home` | в собранном приложении — `FLET_APP_STORAGE_DATA` (своя папка приложения на каждой ОС), либо `FOOTBALL_PROGNOZ_HOME` |

Иконки, заставку и фоновый узор генерирует скрипт (Pillow, только для разработчика):

```bash
python scripts/make_assets.py
```

Готовые PNG уже лежат в репозитории; перезапускать скрипт нужно только после изменения рисунка.

## 2. Общие требования (все платформы)

1. Python 3.11+ и виртуальное окружение с dev-зависимостями (в них есть `flet-cli`):

   ```bash
   python -m venv .venv
   source .venv/bin/activate            # Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   flet --version                       # Flet 0.80.5, Flutter 3.38.7
   ```

2. Git.
3. Flutter SDK 3.38.7. Если его нет в `PATH`, первый `flet build` сам скачает его в `~/flutter/3.38.7` (~1,5 ГБ, 2–5 минут).
4. Собирать из корня репозитория. Результат — `build/<платформа>/`. Кэш Flutter-проекта — `build/flutter`; при странных ошибках: `flet clean` и сборка заново, подробный лог — `-v` или `-vv`.

В сборку Python-кода попадает только `src/` (без тестов, `docs/`, `.env`, `.venv`). Ключи API в приложение не зашиваются: пользователь вводит их в «Настройках», они сохраняются в `.env` в папке данных приложения.

## 3. Команды по платформам

Кросс-сборки нет: macOS и iOS собираются только на Mac, Windows — только на Windows, Linux — на Linux (или WSL). Android и web можно собирать на любой из трёх ОС.

### macOS (`.app`)

Требования: macOS 13+, Xcode 16+ (из App Store) и Command Line Tools (`xcode-select --install`), CocoaPods (`brew install cocoapods`).

```bash
flet build macos                              # build/macos/*.app
flet build macos --arch arm64 x86_64          # универсальная сборка Apple Silicon + Intel
```

Для распространения вне App Store приложение нужно подписать Developer ID и нотарифицировать (`codesign`, `xcrun notarytool`) — без этого Gatekeeper покажет предупреждение (первый запуск: правый клик → «Открыть»).

### Windows (`.exe`)

Требования: Windows 10/11, Visual Studio 2022 (Community подходит) с нагрузкой «Разработка классических приложений на C++», включённый «Режим разработчика» (Параметры → Конфиденциальность и защита → Для разработчиков; нужен для symlink'ов Flutter).

```powershell
flet build windows                            # build\windows\*.exe + DLL
```

Папку `build\windows` целиком можно заархивировать или упаковать в установщик (Inno Setup, MSIX).

### Linux

Требования (Ubuntu 22.04+ / Debian 12+):

```bash
sudo apt install clang lld cmake ninja-build pkg-config libgtk-3-dev liblzma-dev libstdc++-12-dev \
                 libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev xdg-user-dirs
flet build linux                              # build/linux/football_prognoz (+ data/, lib/, python3.12/)
./build/linux/football_prognoz                # запуск
```

`lld` нужен компоновщику Flutter (без него: «Failed to find any of [ld.lld, ld]»). `xdg-user-dirs` нужен уже для запуска: без папки «Документы» Flutter падает с `MissingPlatformDirectoryException` (на обычном рабочем столе она есть; на сервере — `xdg-user-dirs-update`). Всю папку `build/linux` (~113 МБ) можно упаковать в tar.gz, AppImage или .deb.

### Android (APK / AAB)

Требования: JDK 17 и Android SDK. Если их нет, `flet build` предложит скачать их сам (JDK 17 и Android SDK ставятся в домашнюю папку пользователя); с установленным Android Studio используется его SDK.

```bash
flet build apk                                # build/apk/*.apk — установка на телефон напрямую
flet build apk --split-per-abi                # отдельные APK на arm64-v8a / armeabi-v7a / x86_64 (меньше размер)
flet build aab                                # build/aab/*.aab — для Google Play
```

Для Google Play AAB подписывается своим ключом:

```bash
keytool -genkey -v -keystore upload.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
flet build aab --android-signing-key-store upload.jks --android-signing-key-alias upload \
               --android-signing-key-store-password "…" --android-signing-key-password "…"
```

Разрешение `INTERNET` уже в манифесте. Локальный Ollama по `http://` на телефоне не заработает (Android запрещает незашифрованный HTTP) — используйте Ollama Cloud (`https://ollama.com`).

### iOS (`.ipa`)

Требования: Mac, Xcode 16+, CocoaPods, аккаунт Apple Developer (для установки на устройство и TestFlight), сертификат и provisioning profile для `com.npawcompany.footballprognoz`.

```bash
flet build ipa --ios-team-id <TEAM_ID> \
               --ios-provisioning-profile "<имя профиля>" \
               --ios-export-method app-store          # build/ipa/*.ipa (ещё: ad-hoc, development)
```

iOS тоже блокирует `http://` (App Transport Security), поэтому локальный Ollama недоступен, облако работает.

### Web

Есть два варианта.

**а) Статическая сборка (Pyodide, Python в браузере):**

```bash
flet build web                                # build/web — статические файлы
python -m http.server --directory build/web 8000   # проверить локально: http://localhost:8000
flet build web --base-url /football/          # если сайт лежит не в корне домена
```

Ограничение: в браузере Python работает в песочнице Pyodide — у `httpx` нет сокетов, а football-data.org, API-Football и Ollama не разрешают запросы с чужих сайтов (CORS). Кроме того, в Pyodide нет модуля `sqlite3` (проверено: приложение падает при старте с «No module named 'sqlite3'»). Поэтому статическая сборка сейчас **не работает**; она описана только для полноты.

**б) Рекомендуемый web-режим — Python на сервере, интерфейс в браузере:**

```bash
flet run --web --port 8550 src/main.py        # http://<сервер>:8550
```

Все функции работают (запросы идут с сервера). Для постоянного размещения — запуск под systemd/Docker за reverse-proxy (nginx/Caddy) с HTTPS; ключи — в `.env` рядом с `pyproject.toml` или в папке `FOOTBALL_PROGNOZ_HOME`.

## 4. CI (GitHub Actions)

Каждая платформа — на своём раннере: `ubuntu-latest` (linux, apk, aab, web), `windows-latest` (windows), `macos-latest` (macos, ipa). Шаги: checkout → `pip install -e ".[dev]"` → `flet build <target> --yes -v` → upload `build/<target>`. Для Linux перед сборкой поставить пакеты из раздела «Linux». Готовый workflow в репозиторий пока не добавлен.

## 5. Что проверено (30.09.2026, Debian 13, Flet 0.80.5, Flutter 3.38.7)

| Цель | Статус |
|---|---|
| `linux` | ✅ `flet build linux` собрался (~113 МБ), приложение запустилось: заставка → замок ключей на градиентном фоне. Иконки для всех платформ (`flutter_launcher_icons`) и заставки (`flutter_native_splash`) сгенерированы без ошибок |
| `web` (статический) | ⚠ `flet build web` собрался (~71 МБ), но в браузере Python падает: в Pyodide 0.27 модуль `sqlite3` вынесен из стандартной библиотеки («No module named 'sqlite3'»); к тому же HTTP к API из браузера невозможен (см. выше). Статический web не поддерживается |
| web (сервер, `flet run --web`) | ✅ так же запускаются все скриншоты интерфейса при разработке |
| `apk`, `aab` | конфигурация проверена (разрешение, adaptive icon, splash), сборка не запускалась: нужно скачать Android SDK + JDK (~3 ГБ) |
| `macos`, `ipa` | нужен Mac с Xcode — не проверено |
| `windows` | нужна Windows с Visual Studio — не проверено |
| Колёса для Android / iOS | `pydantic-core` есть на `pypi.flet.dev` для cp312 android / ios; остальные зависимости — чистый Python. Реальную установку на телефон не проверяли |
