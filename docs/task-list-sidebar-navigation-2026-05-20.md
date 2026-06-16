# Task List: Centralized Sidebar Navigation

- [x] Remove the local `on_nav_item_selected` handler from `dispatch/screens/sidebar.py`.
- [x] Remove the local `on_nav_item_selected` handler from `dispatch/screens/dashboard.py`.
- [x] Remove the local `on_nav_item_selected` handler from `dispatch/screens/new_job.py`.
- [x] Implement centralized `on_nav_item_selected` handling in `dispatch/app.py`.
- [x] Add focused regression coverage for sidebar click navigation and `History -> View Logs`.
- [x] Run the strongest relevant validation subset and record the result.

Validation recorded on 2026-05-20:

- `py -3 -m compileall dispatch scr`
- `py -3 -m pytest tests/test_ui_ux_closure.py -q`
