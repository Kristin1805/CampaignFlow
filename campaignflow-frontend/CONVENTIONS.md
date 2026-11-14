# CampaignFlow Frontend — Conventions

Rules for writing code in this project. When in doubt, follow what existing files already do.

## 1. Files and folders

- All file and folder names use **kebab-case** (lowercase, words separated by `-`).
- **Pages** live in `src/pages/<name>/` and are named `<name>-page.js`.
  - Example: `src/pages/dashboard/dashboard-page.js`
- **Components** live in `src/components/<group>/` and are named `<name>.js` (no `-page` suffix).
  - Example: `src/components/navigation/sidebar.js`, `src/components/buttons/button.js`
- Empty folders contain a `.gitkeep` file so Git tracks them. Delete it once the folder has real files.

## 2. Functions

- Function names use **camelCase**.
- Functions that return HTML start with `render`:
  - pages: `render<Name>Page` → `renderDashboardPage`
  - components: `render<Name>` → `renderSidebar`, `renderButton`
- Render functions **return an HTML string**. They do not insert anything into the DOM themselves.
- Exception: `renderCurrentPage()` in `routes.js` is the router — it is the only render function that writes to the DOM.

## 3. Imports and exports

- Use **named exports** only (`export function ...`, `export const ...`). No default exports.
- Use relative paths with the `.js` extension: `./` (same folder), `../` (one folder up).
- Import in the file that uses the function, not anywhere else.
- Multiple imports from the same file go on one line:
  `import { renderCurrentPage, navigateTo } from "./config/routes.js";`
- **Modules only define and export.** They must not run code on import (no event listeners, no rendering).
- `src/main.js` is the **only** place that starts the app: loads styles, renders the first page, attaches global listeners.

## 4. Routing

- All routes are in `src/config/routes.js` as an object: **URL path → render function**.
- Keys are URL paths (`'/'`, `'/campaigns'`), not file paths.
- Store the function itself (`renderDashboardPage`), not its result (`renderDashboardPage()`).
- Unknown paths render the 404 page (`renderNotFoundPage`).
- Links are normal `<a href="/path">`. `main.js` intercepts clicks and navigates without a page reload.
- Links to other sites (different origin) are not intercepted and open normally.
- To navigate from code, call `navigateTo('/path')`.

**Adding a new page:**
1. Create `src/pages/<name>/<name>-page.js` with `export function render<Name>Page()`.
2. Import it in `routes.js`.
3. Add `'/<name>': render<Name>Page` to the `routes` object.

## 5. Components

- A component is a function: **parameters in → HTML string out**.
- Everything that differs between uses (text, variant, id…) is a parameter.
- Components do **not** call the API and do **not** keep global state.
- Buttons are `type="button"` by default, so they never submit a form by accident.
- Inputs always have a `<label>` linked with `for` = the input's `id`.

## 6. Pages

- One folder per page in `src/pages/`.
- A page builds its HTML from components.
- A page may request data through `src/services/` (see section 8).
- Only one `<h1>` per page: the page title.

## 7. CSS

**Files** (loaded in `main.js` in this exact order):

| File | Purpose |
|---|---|
| `reset.css` | Removes browser defaults (based on Josh W. Comeau's Modern CSS Reset) |
| `variables.css` | All design tokens (`:root` custom properties) |
| `global.css` | Page-wide base styles (`body` colors, font family) |
| `typography.css` | Headings and text sizes |
| `components.css` | Component styles |

**Tokens**
- Every color, spacing, radius, shadow and font value comes from `variables.css` via `var(--token)`.
- **No hardcoded colors, spacing, radius or font values** outside `variables.css`. (Border widths like `1px` are fine.)
- Token names describe the **role**, not the look: `--color-primary`, not `--purple`.
- Spacing scale: `--space-N` = N × 4px.
- Font sizes use `rem`, not `px`, so they respect the user's browser settings.

**Class names (BEM, kebab-case)**
- Block: `.button`, `.input`
- Modifier (variant): `.button--primary`, `.button--secondary` (two dashes)
- Element (part of a block): `.card__title` (two underscores)

**Breakpoints** (`var()` does not work inside `@media`, so use these exact numbers):
- `768px`: tablet, sidebar collapses
- `1024px`: desktop

## 8. UI vs API

- **All** HTTP requests go through `src/services/`. Never call `fetch` directly from a page or component.
- Components only render. Pages decide what data they need and ask a service for it.
- API paths start with `/api/`. In development Vite proxies them to Django (see README).

## 9. Security

- Never insert user-provided data into an HTML string without escaping it. Content inserted with `innerHTML` is parsed as HTML, so unescaped data can run scripts (XSS).

## 10. General

- **YAGNI** ("You Aren't Gonna Need It"): don't write code or styles for things we don't need yet.
- Branch names: `CF-###` (ticket number).
- Commit messages: `CF-###: Verb what changed` (e.g. `CF-012: Add button component`).