"""
Screen Builder engine (منشئ الشاشات)

- screen_config  : read / validate / save config/screens/<key>.json
- form_inspector : read-only scan of an add form (fields, required, Select2, buttons)
- form_filler    : fills fields from a config, STRICT (never picks another value silently)
- screen_runner  : one generic flow: login -> list -> add -> fill -> save -> verify new row
- cli            : command line entry (inspect / dry-run / run)
"""
