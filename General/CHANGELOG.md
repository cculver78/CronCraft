# Changelog

## 20260329.02

### Marketing & SEO

- Fixed footer alignment issue by overriding flex layout on the wide footer container so elements stack correctly
- Marketing pages: restore black text on green `.btn-primary` and muted text on `.btn-ghost` (prose link styles no longer override buttons)

- Footer link grid: use explicit 4-column (2×4) layout on desktop so columns align horizontally; narrow breakpoints use 2 then 1 column

### Marketing & SEO

- Added ~29 public marketing routes (keyword pages, compare, use cases, integrations, blog) with shared `marketing/layout.html`, canonical + Open Graph tags, and JSON-LD FAQ on the Cronhub alternative page
- Expanded site footer with internal links; homepage Cronhub banner and Resources section; updated `sitemap.xml` with all new URLs
- Registered `marketing` blueprint in the Flask app

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
