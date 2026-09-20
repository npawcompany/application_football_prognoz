# Page: Fixtures

Overrides MASTER for the upcoming-match list (nav index 1).

## Layout
Same 1440×900 desktop chrome. Header row: back (Phosphor `arrow-left`), league name, refresh. Wide split (Календарь): left compact match grid (2 cols, rows ~48–56px), right forecast. Embedded in Лиги split: list without back button.

## Components
- SDS `Card` / `Text List Item` for each match
- SDS `Icon Button` back + refresh
- Compact disclaimer chip (always visible on match/forecast surfaces): statistical forecast, not betting advice. Not a full-width banner.

## Filter
`filter_bar`: search **Команда**. Chips **Предстоящие** (default) / **Все матчи**. Header title is «Предстоящие матчи» or «Матчи» to match the chip.

## Match row
Compact rows 52px (full) / 56px (embedded split). Official club crests (`home_crest` / `away_crest`) 24px · date/time UTC · home vs away · status `SCHEDULED` · button «Прогноз». Entire row is a hit target → Match page. Long club names ellipsize (`overflow` hidden, tooltip = full name); the row does not wrap.

## Chart
None on this page (list only). Probability bars live on Match.

## Empty
Upcoming: «Нет предстоящих матчей в кэше. Нажмите обновить.» All matches: «Нет матчей в кэше. Нажмите обновить.»
