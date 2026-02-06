---
name: Medusa path/layout fixes
overview: The failures come from (1) icon and resource paths being resolved relative to the current working directory instead of the package root, and (2) wrap_path returning False when there is no session, which is then passed to os.path.isfile() and triggers the "bool is used as a file descriptor" warning. The project layout is package-based under src/medusa_platform/; paths must use constants.SRC_ROOT.
todos: []
isProject: false
---

# Medusa platform path and package layout fix plan

## Current package layout (correct structure)

- **Package root**: `[src/medusa_platform/](src/medusa_platform/)` (this is the installable package; `pyproject.toml` uses `packages = ["src/medusa_platform"]`).
- **Entrypoint**: `[src/medusa_platform/main.py](src/medusa_platform/main.py)`. There is no top-level `src/main.py` in the current tree (git shows it deleted).
- **Resources**: Icons and GUI assets live under the package: `src/medusa_platform/gui/images/icons/svg/` (e.g. `search.svg`, `link.svg`, `visibility_login.svg` all exist there).
- **Path constant**: `[src/medusa_platform/constants.py](src/medusa_platform/constants.py)` defines `SRC_ROOT = os.path.dirname(os.path.abspath(__file__))` (i.e. the package root) and `IMG_FOLDER = 'gui/images'`. The project rule already states that UI/resource paths should use `os.path.join(constants.SRC_ROOT, ...)`.

## Root causes

### 1. Icon path is CWD-relative (FileNotFoundError for icons)

In `[src/medusa_platform/gui/gui_utils.py](src/medusa_platform/gui/gui_utils.py)`, `get_icon()` builds the path as:

```python
rel_path = "%s/icons/svg/%s" % (constants.IMG_FOLDER, icon_name)  # e.g. "gui/images/icons/svg/search.svg"
if not os.path.isfile(rel_path):
    raise FileNotFoundError('Icon %s not found!' % rel_path)
```

This is **relative to the current working directory**, not the package. When the app is run from the repo root (e.g. `uv run python -m medusa_platform` or `python -m medusa_platform`), CWD is the repo root, so the code looks for `gui/images/icons/svg/...` under the repo root, which does not exist (icons are under `src/medusa_platform/gui/images/...`).

**Fix**: Resolve the icon path from the package root, e.g.:

- `icon_path = os.path.join(constants.SRC_ROOT, constants.IMG_FOLDER, "icons", "svg", icon_name)`
- Use `icon_path` for both `os.path.isfile()` and the subsequent `open()`.

Single place to change: `[gui_utils.py](src/medusa_platform/gui/gui_utils.py)` in `get_icon()` (around lines 424–427 and the later `open(rel_path, ...)`).

### 2. wrap_path returns False when there is no session (RuntimeWarning: bool as file descriptor)

In `[src/medusa_platform/accounts_manager.py](src/medusa_platform/accounts_manager.py)`, `wrap_path()` returns `False` when `check_session()` is False (no logged-in user):

```python
def wrap_path(self, path):
    if self.check_session():
        ...
        return wrapped_path
    else:
        return False
```

Callers then do `os.path.isfile(gui_config_file_path)` (and similar) without checking. In Python 3.12+, passing `False` into `os.path.isfile()` can trigger “bool is used as a file descriptor” because `bool` subclasses `int` and `False` is 0.

**Fix**: Ensure every use of `wrap_path()` for config files only calls `os.path.isfile()` (or `open()`) when the result is a valid path string.

- **Option A (recommended)**: At each call site, guard with a path check, e.g.  
`gui_config_file_path = self.accounts_manager.wrap_path(constants.GUI_CONFIG_FILE)`  
then use only if it’s a path:  
`if gui_config_file_path and os.path.isfile(gui_config_file_path):`
- **Option B**: Change `wrap_path()` so that when there is no session it returns a path that does not require a session (e.g. a path under CWD or a default config directory) instead of `False`, so call sites can stay as-is. This may change semantics (e.g. where “unauthenticated” config is stored).

**Call sites to update (if using Option A)**:

- `[main_window.py](src/medusa_platform/gui/main_window.py)`: lines 179–182 (gui_config load), 232 (gui_config save), 427–431 (lsl_config load), 777–781 (lsl_config in reset_tool_bar_main / dialog).
- `[app_manager.py](src/medusa_platform/app_manager.py)`: lines 32–33 (`apps_config_file_path`), 46 (`os.path.isfile(self.apps_config_file_path)`).
- `[plots_panel.py](src/medusa_platform/gui/plots_panel/plots_panel.py)`: `plots_config_file_path` is passed in from main_window (which gets it via `wrap_path`); the check at line 57 is `os.path.isfile(self.plots_config_file_path)` — so the value must never be `False` when passed into PlotsPanel; the guard should be in main_window when building/passing `plots_config_file_path` (and when loading/saving LSL/plots config files).

Ensure that for any “load config if exists” pattern, the code only calls `os.path.isfile(...)` and `open(...)` when the variable is a string path, not `False`.

### 3. Stylesheet path and CSS url() (optional follow-up)

- **Stylesheet path**: In `[gui_utils.py](src/medusa_platform/gui/gui_utils.py)`, `set_css_and_theme()` builds the path to `style.css` using `os.path.relpath(os.path.dirname(__file__), os.getcwd())`. That depends on CWD and can break when running from different directories. Prefer resolving the stylesheet path with `constants.SRC_ROOT`, e.g. `os.path.join(constants.SRC_ROOT, "gui", "style.css")`, when `stylesheet_path is None`.
- **CSS content**: `[gui/style.css](src/medusa_platform/gui/style.css)` contains URLs like `url("gui/images/icons/...")`. Those are resolved by Qt relative to CWD (or the app’s working directory). So with CWD = repo root, they would look for `gui/images/...` at repo root and fail. Options: (a) when loading the stylesheet, substitute `gui/images` with an absolute file path (e.g. `file:///.../medusa_platform/gui/images`) in the CSS string, or (b) set a resource prefix and use Qt resources. Fixing (1) and (2) is enough to get the app to start; this can be a follow-up if icons in CSS still don’t show.

### 4. How to run the app (and medusa.bat)

- **Intended run**: From **repo root**, run the package, e.g.  
`uv run python -m medusa_platform`  
or after `uv sync --all-extras`:  
`python -m medusa_platform`  
so that `constants.SRC_ROOT` points to `src/medusa_platform/` and imports resolve correctly.
- **medusa.bat**: The current `[medusa.bat](medusa.bat)` does `cd "src"` and `python "main.py"`, which assumes a flat `src/main.py`. That no longer matches the layout. Update the script to run from the **project root** and execute the package (e.g. activate venv, then `python -m medusa_platform` from repo root, without `cd src`).

## Summary of file-level changes


| Area                  | File                                                                                                       | Change                                                                                                                                                                                                                 |
| --------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Icon path             | `[src/medusa_platform/gui/gui_utils.py](src/medusa_platform/gui/gui_utils.py)`                             | In `get_icon()`, build path with `os.path.join(constants.SRC_ROOT, constants.IMG_FOLDER, "icons", "svg", icon_name)` and use it for existence check and `open()`.                                                      |
| wrap_path / isfile    | `[src/medusa_platform/gui/main_window.py](src/medusa_platform/gui/main_window.py)`                         | Before every `os.path.isfile(wrap_path(...))` or file open on a wrapped path, ensure the wrapped value is not `False` (e.g. `if path and os.path.isfile(path):`). Same for save paths when they come from `wrap_path`. |
| wrap_path / isfile    | `[src/medusa_platform/app_manager.py](src/medusa_platform/app_manager.py)`                                 | When loading apps config, only call `os.path.isfile(self.apps_config_file_path)` (and `open`) when `apps_config_file_path` is not `False`.                                                                             |
| wrap_path / isfile    | `[src/medusa_platform/gui/plots_panel/plots_panel.py](src/medusa_platform/gui/plots_panel/plots_panel.py)` | Ensure `plots_config_file_path` passed from main_window is never `False` when used in `os.path.isfile()`; guard in main_window where the path is created/passed.                                                       |
| Stylesheet (optional) | `[src/medusa_platform/gui/gui_utils.py](src/medusa_platform/gui/gui_utils.py)`                             | In `set_css_and_theme()`, when `stylesheet_path is None`, use `os.path.join(constants.SRC_ROOT, "gui", "style.css")` instead of relpath-from-cwd.                                                                      |
| Launcher              | `[medusa.bat](medusa.bat)`                                                                                 | Run from repo root with `python -m medusa_platform` (and fix venv path if it uses `.vvenv` vs `.venv`).                                                                                                                |


## Optional: QMetaObject connectSlotsByName warnings

The log also shows:

- `QMetaObject::connectSlotsByName: No matching signal for on_app_state_changed(int)`
- `No matching signal for on_run_state_changed(int)`

These come from Qt’s automatic slot naming: a slot named `on_<objectName>_<signal>` is connected to the signal. So either the object names in the UI don’t match, or the signal signatures don’t match `(int)`. Fixing this is independent of the path/layout work; it can be done by aligning the UI object names/signals with the slot names or by connecting those slots explicitly in code.

No edits have been applied; this plan only identifies the correct package layout and where to make the changes.