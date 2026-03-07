# Implementation Plan: 6 Major Features

## Implementation Order
1. **API Rate Limiting** — foundation, backend only
2. **Dashboard Date Range Picker** — extends existing analytics
3. **Notification Center** — new model + API + frontend
4. **AI Drive File Content Analysis** — extends existing services
5. **Gantt Chart / Dependency Graph View** — new frontend page
6. **Offline Support with Service Worker** — must be last, caches everything

---

## Feature 1: API Rate Limiting

### Dependencies
- Add `slowapi==0.1.9` to `requirements.txt`

### Backend Changes (`app/main.py`)
- Import `SlowAPI`, `Limiter`, `_rate_limit_exceeded_handler` from slowapi
- Create Redis-backed limiter: `limiter = Limiter(key_func=get_remote_address, storage_uri=settings.redis_url)`
- Add limiter to app state: `app.state.limiter = limiter`
- Add exception handler for `RateLimitExceeded`
- Apply rate limits via decorator on routers:
  - General API: `60/minute`
  - AI chat endpoints: `10/minute`
  - Auth endpoints: `20/minute`
  - Webhook: `120/minute` (Telegram sends bursts)
  - Health: no limit

### Files Modified
- `requirements.txt` — add slowapi
- `app/main.py` — add limiter middleware + exception handler
- `app/api/router.py` — add `@limiter.limit()` decorators to endpoints

---

## Feature 2: Dashboard Date Range Picker

### Backend Changes (`app/api/router.py`)
- Modify `GET /api/v1/dashboard` to accept `start_date` and `end_date` query params (ISO strings)
- Filter tasks by `created_at` within date range
- Compute stats only for tasks in range
- Default: last 30 days if no params

### Frontend Changes (`app/static/index.html`)

**HTML** — Add date range picker bar above analytics charts:
```html
<div class="dr-bar">
  <div class="dr-presets">
    <button class="dr-btn a" onclick="setDR('7d')">7 Days</button>
    <button class="dr-btn" onclick="setDR('30d')">30 Days</button>
    <button class="dr-btn" onclick="setDR('90d')">90 Days</button>
    <button class="dr-btn" onclick="setDR('year')">This Year</button>
    <button class="dr-btn" onclick="setDR('all')">All Time</button>
  </div>
  <div class="dr-custom">
    <input type="date" id="dr-start" class="inp">
    <span>—</span>
    <input type="date" id="dr-end" class="inp">
    <button class="btn p" onclick="applyDR()">Apply</button>
  </div>
</div>
```

**CSS** — `.dr-bar`, `.dr-presets`, `.dr-btn`, `.dr-custom` styles

**JavaScript**:
- `setDR(preset)` — calculate start/end dates from preset, call `loadAnalytics(start, end)`
- `applyDR()` — read custom date inputs, call `loadAnalytics(start, end)`
- Modify `loadAnalytics(startDate, endDate)` — pass dates as query params to `/dashboard?start_date=...&end_date=...`
- Recalculate all 6 charts with filtered data

**i18n keys**: `dateRange`, `days7`, `days30`, `days90`, `thisYear`, `allTime`, `customRange`, `apply`

---

## Feature 3: Notification Center

### Database — New `notifications` table
```sql
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    message TEXT,
    link VARCHAR(500),
    entity_id INTEGER,
    entity_type VARCHAR(50),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
)
```
Index: `idx_notif_user_read` on `(user_id, is_read)`

### New Model (`app/models/notification.py`)
- `Notification` SQLAlchemy model with fields above
- Types: `task_assigned`, `task_status`, `task_overdue`, `reminder_due`, `comment_added`, `ai_insight`

### New API Endpoints (`app/api/notification_api.py`)
- `GET /api/v1/notifications?unread_only=false&limit=30` — list notifications
- `GET /api/v1/notifications/count` — unread count
- `POST /api/v1/notifications/{id}/read` — mark single as read
- `POST /api/v1/notifications/read-all` — mark all as read
- `DELETE /api/v1/notifications/{id}` — delete notification

### Notification Generation (integrated into existing flows)
- `app/api/router.py` — on task create/update, create notification
- `app/worker.py` — on overdue check, create notification
- `app/api/task_action_api.py` — on comment, create notification
- Helper function `create_notification(db, user_id, type, title, message, entity_id, entity_type)` in a service

### Frontend Changes

**HTML** — Notification bell in sidebar (above language toggle):
```html
<button class="nb" onclick="toggleNotifPanel()" id="notif-btn">
  🔔<span class="l" data-i18n="notifications">Notifs</span>
  <span class="notif-badge" id="notif-badge" style="display:none">0</span>
</button>
```

Notification dropdown panel:
```html
<div class="notif-panel" id="notif-panel">
  <div class="notif-header">
    <h3>Notifications</h3>
    <button onclick="markAllRead()">Mark all read</button>
  </div>
  <div class="notif-list" id="notif-list"></div>
</div>
```

**CSS**: `.notif-badge` (red circle), `.notif-panel` (dropdown), `.notif-item`, `.notif-item.unread`

**JavaScript**:
- `loadNotifCount()` — poll `GET /notifications/count` every 30s, update badge
- `toggleNotifPanel()` — show/hide panel, load notifications
- `loadNotifications()` — fetch and render list
- `markRead(id)` — mark single notification read
- `markAllRead()` — mark all read
- `renderNotifItem(n)` — HTML for each notification with icon by type

**i18n keys**: `notifications`, `markAllRead`, `noNotifications`, `notifTaskAssigned`, `notifStatusChanged`, `notifOverdue`, `notifComment`, `notifReminder`

---

## Feature 4: AI Drive File Content Analysis

### Backend Changes

**New endpoint in `app/api/calendar_api.py`**:
- `POST /api/v1/calendar/events/{event_id}/analyze-attachment`
- Body: `{ attachment_url: str, filename: str }`
- Flow:
  1. Load user's Google OAuth credentials
  2. Extract Drive file ID from attachment URL
  3. Download file bytes from Drive via `drive.files().get_media(fileId=...)`
  4. Process through `file_processor.extract_text_from_file()`
  5. Send extracted content to Claude via `ai_engine.chat_with_file()`
  6. Return analysis result

**New method in `app/services/calendar_svc.py`**:
- `download_from_drive(credentials, file_id) -> bytes` — download file content from Google Drive

### Frontend Changes

**HTML** — In event detail modal, add analyze button per attachment:
```html
<button class="btn gm" onclick="analyzeAttachment(url, name)">🔍 Analyze</button>
```

**JavaScript**:
- `analyzeAttachment(url, filename)` — POST to analyze endpoint, show loading spinner, display result in modal
- Add analysis result area in event modal

**i18n keys**: `analyzeContent`, `analyzing`, `analysisResult`

---

## Feature 5: Gantt Chart / Dependency Graph View

### No database changes required — uses existing tasks + dependencies

### Frontend Changes

**HTML** — New page section:
```html
<div class="pg" id="page-gantt">
  <h2>📊 <span data-i18n="ganttChart">Gantt Chart</span></h2>
  <div class="gantt-toolbar">
    <!-- Filter controls + zoom -->
  </div>
  <div class="gantt-container" id="gantt-container"></div>
</div>
```

Add nav button in sidebar for Gantt page.

**CSS**:
- `.gantt-container` — scrollable horizontal container
- `.gantt-header` — date columns header
- `.gantt-row` — task row with label + bar area
- `.gantt-bar` — colored bar (status-based colors)
- `.gantt-bar-label` — task title inside bar
- `.gantt-dep-line` — SVG arrow line for dependencies
- `.gantt-today` — vertical today line

**JavaScript**:
- `loadGantt()` — fetch tasks + dependency map, render chart
- `renderGantt(tasks, deps)` — build the chart:
  1. Calculate date range (earliest created_at to latest due_date + buffer)
  2. Create header row with date columns (day/week/month scale)
  3. For each task: render horizontal bar from created_at to due_date
  4. Draw SVG dependency arrows between linked tasks
  5. Add today marker line
- `setGanttScale(scale)` — switch between day/week/month zoom
- `ganttFilterGroup(groupId)` — filter by task group
- Click on bar → `openTD(taskId)` to open task detail modal
- Color mapping: todo=blue, in_progress=orange, review=purple, done=green

**i18n keys**: `ganttChart`, `ganttSub`, `ganttScale`, `ganttDay`, `ganttWeek`, `ganttMonth`, `ganttNav`

---

## Feature 6: Offline Support with Service Worker

### New File: `app/static/sw.js`
```javascript
const CACHE_NAME = 'ai-assistant-v1';
const STATIC_ASSETS = ['/', '/static/index.html'];
const API_CACHE = 'api-cache-v1';
const QUEUE_DB = 'offline-queue';

// Install: cache static assets
// Activate: clean old caches
// Fetch: cache-first for static, network-first for API with fallback
// Background sync: retry queued mutations when online
```

### Backend Changes
- `app/main.py` — serve `sw.js` with correct MIME type and no-cache headers
- Add manifest.json route (basic PWA manifest)

### Frontend Changes (`app/static/index.html`)

**HTML** — Offline indicator banner:
```html
<div class="offline-bar" id="offline-bar" style="display:none">
  ⚠️ <span data-i18n="offlineMode">You are offline</span>
  <span class="offline-queue" id="offline-queue-count"></span>
</div>
```

**CSS**: `.offline-bar` — fixed top warning banner (yellow/orange)

**JavaScript**:
- Register service worker at startup
- Listen for online/offline events → show/hide banner
- `queueOfflineAction(method, url, body)` — store failed mutations in IndexedDB
- `syncOfflineQueue()` — replay queued requests when back online
- `showOfflineCount()` — show number of queued changes

**i18n keys**: `offlineMode`, `offlineQueue`, `syncing`, `syncComplete`

---

## Summary of All File Changes

| File | Action | Features |
|------|--------|----------|
| `requirements.txt` | Edit | #1 (slowapi) |
| `app/main.py` | Edit | #1 (rate limit), #3 (notifications table), #6 (sw.js route) |
| `app/api/router.py` | Edit | #1 (decorators), #2 (date range), #3 (notification triggers) |
| `app/models/notification.py` | **New** | #3 |
| `app/api/notification_api.py` | **New** | #3 |
| `app/services/notification_svc.py` | **New** | #3 |
| `app/api/calendar_api.py` | Edit | #4 (analyze endpoint) |
| `app/services/calendar_svc.py` | Edit | #4 (download_from_drive) |
| `app/static/index.html` | Edit | #2, #3, #4, #5, #6 (all frontend) |
| `app/static/sw.js` | **New** | #6 |
| `app/worker.py` | Edit | #3 (notification on overdue) |

## i18n Keys Summary (all new keys)
~30 new keys for both EN and KH translations.
