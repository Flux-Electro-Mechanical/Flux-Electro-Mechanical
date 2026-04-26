# Codebase issue backlog (targeted tasks)

## 1) Typo fix task
**Title:** Correct misspelled company email domain (`enginner` → `engineer`) across app constants and docs.

**Issue found:** The configured contact email uses `fluxelectromechanical.enginner.et` (misspelled domain segment) in runtime code and documentation.

**Primary files:**
- `app.py`
- `README.md`
- `README.txt`

**Suggested acceptance criteria:**
- Replace every `enginner.et` occurrence with the intended domain.
- Verify contact info rendered from `company_email` and default admin email aligns with docs.

---

## 2) Bug fix task
**Title:** Remove duplicated admin nav links and align desktop/mobile admin menus.

**Issue found:** In the shared base template, desktop admin navigation duplicates `Testimonials` and `Projects Admin` links, while the mobile admin menu omits `Testimonials`.

**Primary file:**
- `templates/base.html`

**Suggested acceptance criteria:**
- Desktop admin menu contains each admin section link exactly once.
- Mobile admin menu contains the same admin destinations as desktop (including Testimonials).
- A quick template render check confirms no duplicated admin links.

---

## 3) Comment/documentation discrepancy task
**Title:** Reconcile homepage testimonial implementation with README release note.

**Issue found:** README claims homepage testimonials now load from database, but `templates/index.html` still contains an earlier hard-coded sample testimonial slider section in addition to DB-driven testimonials.

**Primary files:**
- `README.md`
- `README.txt`
- `templates/index.html`

**Suggested acceptance criteria:**
- Decide on intended behavior: fully DB-driven testimonials, or mixed sample + DB.
- Update template and/or docs so they match exactly.
- If sample slider remains intentionally, document it explicitly in README.

---

## 4) Test improvement task
**Title:** Add regression tests for navigation consistency and testimonial source behavior.

**Issue found:** No automated tests currently guard against template regressions such as duplicate admin links or mismatch between sample and DB testimonial rendering.

**Suggested test scope:**
- Add Flask route/template tests (e.g., pytest + test client) to verify:
  - Admin nav links are unique in desktop and parity is maintained in mobile nav.
  - Homepage behavior for testimonials matches chosen product behavior (DB-only or mixed).

**Suggested acceptance criteria:**
- New tests fail on the current duplicated-link behavior.
- Tests pass once navigation/template behavior is corrected.
- Tests run in CI/local with documented command in README.
