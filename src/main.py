"""Entry point for `flet build` and `flet run` (app path `src`, module `main`).

flet build runs this module as `__main__`; the package entry point stays
`football_prognoz.main:run` (`football-prognoz` console script).
"""

from football_prognoz.main import run

run()
