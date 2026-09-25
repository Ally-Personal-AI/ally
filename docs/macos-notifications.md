# macOS Native Attention

Ally has two macOS notification paths with deliberately different status.

## Signed desktop path

The production desktop direction is app-owned modern User Notifications.

The signed Swift app:

1. checks `UNUserNotificationCenter` authorization;
2. asks Ally Core/bridge to prepare one bounded proactive cycle;
3. receives only payload-minimized notification candidates;
4. checks the app's already-delivered and pending request identifiers;
5. schedules missing notifications with the deterministic delivery key;
6. acknowledges each exact native result back to Ally; and
7. completes the durable service-cycle record from Ally-owned counters.

The sink identity remains:

```text
macos.notification
```

Keeping the same durable sink ID preserves delivery history across the migration
from the old Python adapter.

The bridge cannot accept a caller-selected notification title, body, identifier,
sink, sound, event payload, attempt count, or failure count.

### Duplicate suppression

Each candidate uses:

```text
attention:macos.notification:<event-uuid>
```

as its `UNNotificationRequest.identifier`.

Before adding a request, the app checks both pending requests and notifications
still visible in Notification Center. If the identifier is already present, the
app reports success back to Ally instead of scheduling a second alert.

SQLite success remains the durable source of truth. Notification Center lookup
is a recovery layer for the case where OS delivery succeeded but the app exited
before Ally persisted the acknowledgement.

### Authorization

Notification permission is explicit and independent from background-service
registration.

The desktop uses `UNUserNotificationCenter.notificationSettings()` before
delivery and requests alert/sound permission only after an explicit user action.
Denied or unavailable delivery becomes an explicit failed attempt in Ally's
durable history rather than disappearing.

### Background proactivity

The current signed-app background model uses `SMAppService.mainApp` as an
explicit launch-at-login registration.

This intentionally keeps one signed application identity responsible for:

- notification authorization;
- `UNUserNotificationCenter` delivery;
- proactive-cycle orchestration; and
- the desktop UI.

If macOS reports `requiresApproval`, Ally directs the user to Login Items
settings.

This is a conservative release-stage design: proactivity continues while the
main Ally app process is running and Ally can launch at login when the user opts
in. A future quit-resistant background agent should be introduced only after its
cross-process identity/notification behavior can be validated on the dedicated
Mac.

### Legacy launchd migration

A historical installation may still have
`~/Library/LaunchAgents/ai.ally.proactive-service.plist`. The signed app checks
that state through Ally Core before registering or running automatic proactivity.

The app may retire only a recognized Ally-owned definition. A historical
absolute Python executable path is allowed to differ, but every other plist
field must match Ally's deterministic legacy definition. Symlinks and modified
plists are reported for manual review and are never deleted automatically.

While any legacy definition remains configured—or migration state cannot be
verified—the signed app pauses automatic proactive cycles and refuses to enable
the modern login item. This prevents two schedulers from being intentionally
left active even though the shared runtime lease already protects the actual
cycle from overlap.

## Notification text privacy

Notification Center is an intentional user-facing disclosure surface. Content
may be visible on the desktop or lock screen according to the user's macOS
preview settings.

Both modern and legacy adapters share one backend-neutral renderer. It emits:

- title `Ally`, or `Ally — Important` for interrupt attention;
- the first non-empty explicit string field `summary` or `message`; otherwise
- the event type.

Text is whitespace-normalized and bounded to 500 characters.

Nested payloads, arbitrary fields, credentials, model context, memories, and
document content are never implicitly copied into notification candidates.

Delivery history persists only safe error classes / fixed safe error labels, not
notification text or arbitrary native exception messages.

## Durable lifecycle

Preparing a cycle with notification candidates leaves the service-cycle record
`running`.

Each exact native acknowledgement increments durable attempt/failure counters.
Only `service.complete_proactive` may move the run to:

- `succeeded` when all acknowledged delivery attempts succeeded; or
- `degraded` when one or more native delivery attempts failed.

The completion call accepts only the run ID. It cannot supply metrics.

If Ally exits before completion, the next lease-protected cycle marks the old
run `interrupted`. Notification identifiers can then reconcile already
scheduled/delivered requests without duplicate alerts.

Delivery success still does **not** mark the underlying event handled.

## Legacy CLI compatibility

The old CLI/launch-agent adapter remains isolated in
`ally.attention.macos` and uses deprecated
`NSUserNotificationCenter`.

It exists for compatibility and deterministic migration testing only. The signed
desktop release path does not import or call that backend.

Manual legacy commands remain available:

```bash
ally attention deliver --sink macos
ally attention health --sink macos
```

The legacy health adapter still reports authorization as `unobservable`.

Do not use the deprecated adapter as evidence that the signed desktop
notification identity is accepted. Dedicated-machine acceptance must exercise
the bundled app.

## Dedicated-machine acceptance

Before closing the native-attention milestone:

1. install the signed/notarized `Ally.app`;
2. request notification permission from the app and record the resulting
   authorization state;
3. create synthetic mention-later, notify, and interrupt events;
4. run an app-owned proactive cycle and verify exactly one visible notification
   per event;
5. interrupt the app after native delivery but before acknowledgement and
   confirm restart reconciliation does not duplicate the alert;
6. deny notification permission and confirm failed delivery is recorded without
   leaking native error details;
7. verify only the explicit synthetic summary appears in notification content;
8. if a legacy `ai.ally.proactive-service` launch agent exists, confirm the app
   detects it and blocks modern background proactivity until migration;
9. confirm a recognized historical definition can be retired, while a modified
   or symlinked definition is refused and requires manual review;
10. enable/disable background proactivity and verify `SMAppService` state tracks
    Login Items settings;
11. restart/login and verify the signed app identity retains the intended
    notification/background authorization; and
12. confirm legacy launchd/NSUserNotificationCenter delivery is not active in
    the accepted desktop configuration.

For the overall order and stop conditions, start with
[Unified First-Machine Acceptance](hardware/first-machine-acceptance.md).
