# Changelog

## 20260320.00

### Tweaks and Optimizations

- Extracted `_record_alert` and `_get_user_plan` helpers in `alerting.py` to eliminate 3x duplicated Alert creation blocks
- Replaced `if not allowed: pass / else:` anti-pattern with guard-clause conditions in `alerting.py`
- Moved `is_feature_allowed` import to file level in `alerting.py`
- Extracted `_is_team_admin` helper in `teams.py` to replace 3x duplicated authorization patterns
- Removed redundant `len(password) < 8` check in `auth.py` (already handled by `validate_password`)
- Moved `import ipaddress` to file-level in `validators.py`
- Aligned `User.created_at` default with other models in `user.py` (consistent naive-UTC pattern)
- Fixed operator precedence: `not x in (...)` → `x not in (...)` in `dashboard.py`
- Moved inline `from datetime import ...` to file-level in `stripe_routes.py`
- Removed unused `render_template` import in `email_service.py`
- Fixed import order (stdlib before app) in `run.py`
