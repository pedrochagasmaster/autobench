# Centralized Sidebar Navigation and Flat Screen Stack Plan

## Goal

Switching pages using the mouse in the sidebar was unreliable:

1. Screens other than `DashboardScreen` and `NewJobScreen` did not consistently handle `NavItem.Selected`.
2. Clicking a sidebar item from `NewJobScreen` could dismiss the current screen without navigating to the selected target.
3. Repeated `push_screen()` navigation could build an unnecessarily deep screen stack and make `Back` / `Escape` behavior inconsistent.

The navigation flow is centralized in `DispatchApp` so sidebar clicks behave the same way in every screen state and the stack stays flat.

## Proposed changes

### App shell

Modify `dispatch/app.py`:

- Handle `NavItem.Selected` in `DispatchApp`.
- Resolve the active screen from the app, not from per-screen handlers.
- Flatten the screen stack back to `[default, DashboardScreen]` before opening a new top-level destination.
- Route `overview`, `new_job`, `history`, and `browse` through the centralized handler.
- Resolve `view_logs` against the selected job in `DashboardScreen` or `HistoryScreen`, and show a warning when no job is selected.

### Screen cleanup

Modify `dispatch/screens/sidebar.py`:

- Remove the local `on_nav_item_selected` handler so sidebar messages bubble to the app.

Modify `dispatch/screens/dashboard.py`:

- Remove the local sidebar navigation handler and let the app own top-level navigation.

Modify `dispatch/screens/new_job.py`:

- Remove the local sidebar navigation handler and let the app own top-level navigation.

## Verification plan

### Automated

Run:

```bash
py -3 -m compileall dispatch scr
py -3 -m pytest tests/test_ui_ux_closure.py -q
```

### Manual

Start the app with mocks:

```bash
source mocks/dev-env.sh
DISPATCH_MOCK_SCENARIO=happy_path py -3 -m dispatch
```

Verify:

1. Clicking `History` from `Overview` opens `HistoryScreen`.
2. Clicking `Browse` from `History` opens `BrowserScreen`.
3. Clicking `New Job` from `Browse` opens `NewJobScreen`.
4. Clicking `Overview` from `NewJobScreen` returns to the dashboard.
5. Clicking `View Logs` from `Browse` warns that a job must be selected from `Overview` or `History`.
6. Clicking `View Logs` from `History` with a selected row opens `JobDetailScreen`.
7. Clicking `Overview` from `JobDetailScreen` returns to the dashboard without leaving extra screens on the stack.
