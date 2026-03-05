# Plan: Toolbar UX Cleanup - Connection State & Consistency

## Problem

The plugin has a confusing UX with multiple entry points for configuration:
1. **Toolbar "Connect" button** opens the connection dialog
2. **Menu "Settings"** also opens the same connection dialog
3. **Browser panel** shows the OAPIF connection under "WFS / OGC API - Features"
4. No visible indicator of which server the toolbar buttons talk to
5. All action buttons are always enabled, failing at runtime with warnings
6. OAPIF connection's Bearer token expires silently, breaking Browser panel layer browsing while the plugin still appears functional

## Goal

Make the toolbar self-documenting: show connection state, disable actions when disconnected, support disconnect, and keep the OAPIF token alive.

## Design Decisions (from expert review)

| Decision | Rationale |
|----------|-----------|
| Use `QToolButton` with dropdown menu instead of QAction + QLabel | Single widget, conventional QGIS pattern (DB Manager style), handles connect/disconnect/display in one place, avoids QLabel alignment issues across platforms |
| Keep "Connection Settings..." in menu (renamed from "Settings") | Accessibility fallback for users who hide toolbars. Removing it saves 5 lines but loses discoverability |
| Add lightweight disconnect flow | Small effort (clear client, disable actions, update button). Without it, switching servers leaves stale auth configs |
| "Connected" on startup means "credentials loaded," not "server verified live" | Don't block QGIS startup with network calls. Same pattern as DB Manager |
| Add OAPIF token refresh via QTimer | The APIHeader auth config stores a static Bearer token that expires. Without refresh, the Browser panel silently breaks |

## Changes

### 1. QToolButton with dropdown menu (replaces plain Connect QAction)

The connect button becomes a `QToolButton` with `MenuButtonClick` popup mode:

- **Disconnected state**: Button text = "Connect to OpenSPP", standard connect icon
- **Connected state**: Button text = truncated server hostname (e.g., "openspp.example.org"), green-tinted or checkmark icon
- **Click**: Always opens the connection dialog
- **Dropdown menu**:
  - When disconnected: "Connect..." (same as click)
  - When connected: server URL (disabled, informational), separator, "Change Connection...", "Disconnect"

**Implementation**:
- Replace the `add_action()` call for connect with a manually created `QToolButton`
- Add to toolbar via `self.toolbar.addWidget()`
- Store the wrapper `QAction` from `addWidget()` for proper cleanup in `unload()`

**Files**: `openspp_plugin.py`

### 2. Disable action buttons when not connected

- On plugin load: if no saved connection, disable Stats/Proximity/Geofence/Export buttons
- After successful connection: enable them
- After disconnect: disable them
- Keep the runtime `if not self.client` checks as a safety net
- The connect button itself always remains enabled

**Implementation**:
- Store references to action buttons as named attributes (e.g., `self.action_stats`) in addition to keeping them in `self.actions`
- Add `_set_actions_enabled(enabled: bool)` that toggles the 4 action buttons (not the connect button)
- Call from `_load_connection()`, `show_connection_dialog()`, and `_disconnect()`

**Files**: `openspp_plugin.py`

### 3. Rename "Settings" to "Connection Settings..." (menu-only)

- Rename the menu item from "Settings" to "Connection Settings..."
- Keep it menu-only (`add_to_toolbar=False`) as it is today
- Remove the separator before it (unnecessary with the rename)
- Update `show_settings()` to remain a simple alias for `show_connection_dialog()`

**Files**: `openspp_plugin.py`

### 4. Disconnect flow

New `_disconnect()` method:
- Set `self.client = None`
- Call `_set_actions_enabled(False)`
- Call `_update_connection_state()`
- Stop the token refresh timer
- Optionally clear the stored credentials (ask user? or just disconnect the session without clearing saved creds, so next QGIS launch reconnects)

**Decision**: Disconnect clears the in-memory client but does NOT delete saved credentials. Next QGIS launch will auto-reconnect. This matches how DB Manager handles disconnect (session-only). If the user wants to fully remove credentials, they use "Change Connection..." and enter new ones.

**Files**: `openspp_plugin.py`

### 5. OAPIF token refresh

**The problem**: The APIHeader auth config (`connection_dialog.py:427-503`) stores a pre-acquired Bearer token. The plugin's `OpenSppClient` handles its own token refresh internally (`client.py:118-131`), but the OAPIF connection's stored token is never updated. When it expires, the Browser panel gets silent 401s.

**The solution**: A `QTimer` that periodically refreshes the APIHeader auth config's token before expiry.

**Implementation**:
- Add `_start_token_refresh_timer()` and `_stop_token_refresh_timer()` to `openspp_plugin.py`
- After connection is established, start a timer that fires at `(expires_in - TOKEN_REFRESH_MARGIN) * 1000` ms
- On timer fire, call `self.client.get_token()` (which auto-refreshes if needed) and update the APIHeader auth config in the auth manager
- Extract the APIHeader update logic from `ConnectionDialog._create_apiheader_auth_config()` into a shared utility (or a method on `OpenSppClient`) so both the dialog and the timer can use it
- Stop the timer on disconnect and `unload()`

**Token refresh flow**:
```
Timer fires (5 min before expiry)
  -> self.client.get_token()  # refreshes JWT if needed
  -> load APIHeader config from auth manager (using stored config ID)
  -> update config map with new Bearer token
  -> auth_manager.updateAuthenticationConfig(config)
  -> restart timer for next cycle
```

**Edge cases**:
- Token refresh fails (server down): log warning, retry on shorter interval (e.g., 60s), update connection state to show degraded status
- QGIS was suspended/sleeping: QTimer fires on wake, token may already be expired, `get_token()` will re-authenticate
- Multiple refresh attempts: `get_token()` is idempotent, safe to call multiple times

**Files**: `openspp_plugin.py`, `connection_dialog.py` (extract helper), possibly `client.py` (add token expiry accessor)

### 6. Connection state management (`_update_connection_state()`)

Central method that updates all UI elements based on connection state:
- Updates QToolButton text and icon
- Updates dropdown menu items
- Calls `_set_actions_enabled()`
- Must be idempotent (no flicker when called twice with same state)

Called from: `_load_connection()`, `show_connection_dialog()`, `_disconnect()`, and token refresh failure handler.

**Files**: `openspp_plugin.py`

## Summary of file changes

| File | Changes |
|------|---------|
| `openspp_plugin.py` | QToolButton with dropdown, named action refs, `_set_actions_enabled()`, `_update_connection_state()`, `_disconnect()`, token refresh timer, rename Settings, cleanup in `unload()` |
| `connection_dialog.py` | Extract `_create_apiheader_auth_config()` update logic into reusable function (or move to a shared utility) |
| `client.py` | Add `token_expires_at` property (read-only) so the plugin can schedule the timer accurately |

No changes to `stats_panel.py`, `proximity_dialog.py`, or `geofence_dialog.py`.

## What we're NOT changing

- Browser panel behavior (it's native QGIS, we can't control it)
- Connection dialog UI (it works well as-is)
- Stats panel (unrelated)
- Multi-server support (out of scope, single-server is correct for now)

## Trade-offs

- **Pro**: Conventional QGIS toolbar pattern (QToolButton with dropdown)
- **Pro**: Connection state is always visible; actions grayed out when disconnected
- **Pro**: Token refresh prevents silent OAPIF breakage
- **Pro**: Disconnect flow prevents stale state confusion
- **Con**: Token refresh adds a timer and auth manager writes during the session
- **Con**: Still single-server only, but that matches current architecture
- **Con**: Browser panel still shows OAPIF connection separately; we can't unify that without a custom data provider (much larger scope)

## Task checklist

### Phase 1: Token expiry accessor
- [x] Add read-only `token_expires_in` property to `OpenSppClient` that returns seconds until current token expires (or 0 if no token)
- [x] Write tests for `token_expires_in` (no token, valid token, expired token)

### Phase 2: Reusable APIHeader update
- [x] Extract APIHeader auth config update logic from `ConnectionDialog._create_apiheader_auth_config()` into a standalone function (e.g., `update_oapif_auth_token(bearer_token)` in a new `openspp_qgis/auth.py` module)
- [x] Have `ConnectionDialog._create_apiheader_auth_config()` call the extracted function
- [x] Write tests for the extracted function (create new config, update existing config, handle missing config)

### Phase 3: QToolButton with dropdown
- [x] Replace the Connect `add_action()` call in `initGui()` with a `QToolButton`
- [x] Set `QToolButton.setPopupMode(QToolButton.MenuButtonClick)`
- [x] Create dropdown `QMenu` with connect/disconnect actions
- [x] Add to toolbar via `addWidget()`, store the wrapper `QAction` for cleanup
- [x] Verify the connect button works (click opens dialog, dropdown shows menu)

### Phase 4: Action button management
- [x] Store named references to the 4 action buttons (`self.action_stats`, `self.action_proximity`, `self.action_geofence`, `self.action_export`)
- [x] These are aliases; actions remain in `self.actions` for cleanup
- [x] Add `_set_actions_enabled(enabled: bool)` method (does NOT touch connect button)
- [x] Call `_set_actions_enabled(False)` during `initGui()` (before `_load_connection()`)
- [x] Call appropriate state after `_load_connection()` based on whether `self.client` is set

### Phase 5: Connection state display
- [x] Add `_update_connection_state()` method
- [x] When connected: set button text to server hostname, update icon, enable actions
- [x] When disconnected: set button text to "Connect to OpenSPP", update icon, disable actions
- [x] Update dropdown menu (show/hide disconnect, show server URL)
- [x] Ensure idempotent (calling twice with same state causes no flicker)
- [x] Call from `_load_connection()`, `show_connection_dialog()`, `_disconnect()`

### Phase 6: Disconnect flow
- [x] Add `_disconnect()` method: clear `self.client`, stop token timer, call `_update_connection_state()`
- [x] Wire disconnect to dropdown menu action
- [x] Disconnect does NOT clear saved credentials (session-only)
- [x] Write tests for disconnect state transitions

### Phase 7: OAPIF token refresh timer
- [x] Add `_start_token_refresh_timer()`: schedule QTimer based on `client.token_expires_in`
- [x] On timer fire: call `client.get_token()`, then `update_oapif_auth_token()`, then reschedule
- [x] Add `_stop_token_refresh_timer()`: stop and clean up timer
- [x] Start timer after successful connection (in `show_connection_dialog()` and `_load_connection()`)
- [x] Stop timer in `_disconnect()` and `unload()`
- [x] Handle refresh failure: log warning, retry in 60s, optionally show degraded state
- [x] Write tests for timer scheduling and token update

### Phase 8: Menu cleanup
- [x] Rename "Settings" to "Connection Settings..." in `initGui()`
- [x] Remove the menu separator before it
- [x] Keep `show_settings()` as alias for `show_connection_dialog()`

### Phase 9: Cleanup
- [x] Update `unload()` to remove QToolButton wrapper action, stop timer, clean up menu
- [x] Verify no ghost spacers or leaked widgets after unload/reload cycle
- [x] `settings.svg` kept (still used by "Connection Settings..." menu item)

### Phase 10: Testing
- [x] Test startup with no saved connection (buttons disabled, button shows "Connect to OpenSPP")
- [x] Test startup with saved connection (buttons enabled, button shows server hostname)
- [x] Test connect flow (buttons enable, button text updates, timer starts)
- [x] Test disconnect flow (buttons disable, button text resets, timer stops, saved creds persist)
- [x] Test reconnect after disconnect (same flow as fresh connect)
- [x] Test token refresh timer fires and updates APIHeader config
- [x] Test token refresh failure (logs warning, retries)
- [x] Test `unload()` properly cleans up QToolButton wrapper action and timer
- [x] Test `_update_connection_state()` is idempotent
- [ ] Manual verification in QGIS (requires QGIS installation)
