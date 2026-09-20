# Page: Fixtures

Overrides MASTER for the upcoming-match list (nav index 1).

## Layout
Same 1440×900 desktop chrome. Header row: back (Phosphor `arrow-left`), league name, refresh. Wide split (Календарь): left compact match grid (2 cols, rows ~48–56px), right forecast. Embedded in Лиги split: list without back button.

## Components
- SDS `Card` / `Text List Item` for each match
- SDS `Icon Button` back + refresh
- Compact disclaimer chip (always visible on match/forecast surfaces): statistical forecast, not betting advice. Not a full-width banner.

## Match row
Official club crests (`home_crest` / `away_crest`) 28px · date/time UTC · home vs away · status `SCHEDULED` · button «Прогноз». Entire row is a hit target → Match page.

## Chart
None on this page (list only). Probability bars live on Match.

## Empty
«Нет предстоящих матчей в кэше. Нажмите обновить.»
