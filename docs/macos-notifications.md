# macOS Native Attention

Ally's proactive attention runtime can deliver user-facing events through macOS
Notification Center while preserving the same durable delivery state used by
other sinks.

## Current adapter

During Ally's CLI/launch-agent phase, the native sink uses Foundation's
`NSUserNotificationCenter` through a narrow ctypes/Objective-C bridge.

This API is deprecated by Apple, but unlike the modern
`UNUserNotificationCenter` path it does not require Ally to already have a
bundled desktop application. The deprecated API is isolated behind
`MacOSNotificationSink` and can be replaced without changing event,
delivery-history, retry, or service-cycle contracts.

The future bundled desktop shell should replace this backend with
`UNUserNotificationCenter`, which provides first-class notification
authorization state and is the long-term platform API.

## Delivery identity and retries

The sink ID is:

```text
macos.notification
```

Ally derives a stable notification identifier from the sink ID and event UUID.
Before native delivery, the adapter checks Notification Center's delivered
notifications for that identifier. This provides a second duplicate-suppression
layer in addition to Ally's durable successful-delivery record.

A successful delivery is still terminal only for the event/sink pair. It does
not mark the underlying Ally event handled.

## Notification text privacy

Notification Center is an intentional user-facing disclosure surface. Content
may be visible on the desktop or lock screen according to the user's macOS
notification-preview settings.

The native sink therefore never serializes the complete event payload.

It renders:

- title `Ally`, or `Ally — Important` for interrupt attention;
- the first non-empty string in explicit payload field `summary` or
  `message`; otherwise
- the event type.

Rendered text is whitespace-normalized and bounded to 500 characters.
Nested payloads, arbitrary fields, credentials, model context, memory, and
document content are never implicitly copied into a notification.

Delivery failures persist only the exception class through the existing
attention runtime. Native error details and notification text are not copied to
delivery history or service lifecycle logs.

## Sink selection

Manual delivery remains console-first unless explicitly selected:

```bash
ally attention deliver --sink macos
```

Inspect payload-free readiness:

```bash
ally attention health --sink macos
ally attention health --sink macos --json
```

The bounded proactive service defaults to `--sink auto`:

- macOS -> native Notification Center;
- other platforms -> console.

The opt-in macOS launch agent invokes that same default service-cycle path.

## Authorization limitation

The CLI-compatible legacy native API does not expose the modern notification
authorization state reliably. Health therefore reports authorization as
`unobservable` and a degraded state until dedicated-machine acceptance
confirms notifications are visible and correctly configured.

The health contract already supports `authorized`, `denied`,
`not_determined`, and `unobservable` states so the future bundled
`UNUserNotificationCenter` backend can report denial directly without
changing the command contract.

Do not infer permission from a successful API call alone.

For the overall dedicated-machine order and stop conditions, start with
[Unified First-Machine Acceptance](hardware/first-machine-acceptance.md).

## Dedicated-machine acceptance

Before closing the native-attention milestone:

1. run `ally attention health --sink macos`;
2. emit synthetic mention-later, notify, and interrupt events;
3. deliver through the native sink and confirm one user-visible notification per
   event;
4. retry the same events and confirm successful deliveries are not duplicated;
5. change notification settings/preview settings and document observed behavior;
6. verify notification content contains only the explicit synthetic summary;
7. confirm failed attempts persist only safe exception classes;
8. restart/login and confirm the managed service continues native delivery.

Permission-denial behavior must be observed on the dedicated machine. The
future bundled desktop backend should then replace the legacy adapter with
modern authorization-aware User Notifications.
