# Fermax DuoxMe APK: how the incoming-call notification is built

This document summarizes behavior reverse-engineered from the Fermax Android app (APK decompiled with jadx, e.g. `Fermax_DuoxMe-4.2.6.apk`). Use it as a checklist if you want **similar urgency and presentation** from Home Assistant (e.g. via the [Companion app](https://companion.home-assistant.io/docs/notifications/notifications-basic/)).

Local reference in this repo (when `apk-decompiled/` is present):

- `apk-decompiled/sources/com/fermax/blue/app/ui/viewmodels/NotificationViewModel.java`
- `apk-decompiled/sources/com/fermax/blue/app/data/notifications/controllers/MediasoupController.java`
- `apk-decompiled/sources/com/fermax/blue/app/core/base/BaseActivity.java`
- `apk-decompiled/resources/AndroidManifest.xml`

---

## End-to-end flow

1. **FCM data message** arrives (type includes doorbell / call; the app routes by `FermaxNotificationType`).
2. **`MediasoupController`** parses payload, resolves caller info, sends a **local broadcast** to wake the in-app call path, then calls **`NotificationViewModel.buildIncomingCallNotification(...)`**.
3. The view model **recreates the notification channel**, builds a **NotificationCompat** with category **call**, optional **full-screen intent**, then **`notify(tag, id, notification)`**.

Generic info pushes use **`buildTextNotification`** on the default channel (`IMPORTANCE_DEFAULT`, notification-class sound). Incoming calls use a **separate high-importance channel** and richer styling (below).

---

## Notification channel (incoming calls)

Before showing the notification, the app calls **`removeDeprecatedNotificationChannels()`** and **`buildIncomingCallsChannel(melody)`**:

| Property | Value |
|----------|--------|
| Channel id | `IncomingCall_v6_` + pseudo-random suffix (`Random(1L).toString()`), stored in prefs via `DeviceViewModel.setCallChannelId` |
| Importance | **4** = `IMPORTANCE_HIGH` |
| Sound | Raw resource name from `whichIsTheMelody(callAs)`, or **`RingtoneManager.getDefaultUri(1)`** when melody is `ringtone_default` |
| Audio usage | **6** (`USAGE_NOTIFICATION_RINGTONE`) with content type **4** (`CONTENT_TYPE_SONIFICATION`) |
| Vibration | Enabled, pattern `{500, 200, 500, 400, 500}` ms |

**Default** (non-call) channel uses importance **3** (`IMPORTANCE_DEFAULT`) and `RingtoneManager.getDefaultUri(2)` (notification stream).

---

## Incoming-call notification payload

Built with **`NotificationCompat.Builder`**, channel **`IncomingCall_v6_` + `randomNumber`**:

| Feature | Implementation |
|---------|----------------|
| Small icon | `R.drawable.ic_accept_call` |
| Title / body | Localized `title` and `body` from push |
| Large icon + style | **`BigPictureStyle`**: `largeIcon` and `bigPicture` from **`imageUseCase.get(HOUSE, currentUser, callAs)`** (house image bitmap) |
| Priority | **`setPriority(1)`** → `PRIORITY_HIGH` |
| Category | **`setCategory("call")`** → Android **`Notification.CATEGORY_CALL`** |
| Visibility | **`VISIBILITY_PUBLIC` (1)** |
| Timeout | **`setTimeoutAfter(30_000)`** (constants align with `NOTIFICATION_TIMEOUT`) |
| Tap action | **`PendingIntent.getActivity`** → **`CallActivity`** intent processed by **`BaseCallActivity.addExtras(...)`** (device id, call-as, room, signaling URL, timeouts, streaming mode, flags including “turn screen on” / full-screen path) |
| Posted as | **`notify(deviceId + "/" + callAs, CallNotificationID.getNewId(), notification)`** so updates/cancel use a **stable tag** per device + monitor |

After `build()`, the code sets **`notification.flags = 20`** (decompiler output: **16 | 4** → **`FLAG_AUTO_CANCEL` | `FLAG_INSISTENT`** in Android’s `Notification` API).

---

## Full-screen (“take over like a phone call”) behavior

Declared in the manifest: **`android.permission.USE_FULL_SCREEN_INTENT`**.

**`setFullScreenIntent(pendingIntent, true)`** is applied only when **all** of the following hold:

- **`POST_NOTIFICATIONS`** granted
- Device is **not** locked (`!isDeviceLocked`)
- Screen is **off** (`!isDeviceScreenOn`)
- **`fullScreenNotificationSettingUseCase.isEnabledById(callAs)`** is true (per-monitor/user setting in the app)

The full-screen **`PendingIntent`** targets the same **`CallActivity`** pattern but **`BaseCallActivity.addExtras`** differs from the tap intent in at least one boolean (jadx shows an extra flag set to **`true`** in the full-screen branch vs **`false`** for the normal content intent—likely “opened from full-screen” for `CallViewModel`).

If **`TurnScreenOn.forDeviceId(callAs)`** is true, the app **forces full-screen notification setting off** for that id before building (`fullScreenNotificationSettingUseCase.set(false, callAs)`).

---

## How the app detects an active “call” notification

**`BaseActivity.checkForActiveCallNotification()`** scans **`NotificationManager.getActiveNotifications()`** and looks for **`notification.category` equals `"call"`**, then **`send()`s** the notification’s **`contentIntent`** to jump into the call UI—useful when resuming the app while a call notification is still posted.

---

## Mapping ideas for Home Assistant (Companion app)

The Companion app is **not** the Duox app: you cannot reproduce Fermax’s **`CallActivity`** or their exact channel churn without a custom Android app. You **can** approximate pieces:

1. **High-importance Android channel**  
   Create a dedicated channel in Companion, set importance to **Urgent / high** in Android settings, and send notifications with `channel` set to that id so the device treats alerts like ringtone-class traffic.

2. **Priority and persistence**  
   Use `priority: high` (and platform-specific fields documented for [mobile_app notify](https://www.home-assistant.io/integrations/mobile_app/#notify)) so FCM delivers prominently.

3. **Rich layout**  
   Use `image` / attachment URLs for a **large image** or expanded style where the integration supports it (behavior varies by Android version and Companion version).

4. **Deep link on tap**  
   Use `url` / `clickAction` (per Companion docs) to open a **Lovelace view**, the Duox card, or `homeassistant://` URIs so tap-to-answer matches “open the intercom” mentally.

5. **Critical / time-sensitive (especially iOS)**  
   For true “break through Focus,” use the documented **critical notification** paths for iOS; Android’s analog is channel importance + full-screen intents, which **only your notified app** may use—Companion exposes what it exposes; check current docs for `sticky`, alarms, or full-screen–related options.

6. **Insistent / repeat**  
   Duox sets **insistent** on the notification; HA may need **automations** (repeat notify, TTS, or smart speaker) if the mobile integration does not mirror `FLAG_INSISTENT`.

7. **Tag + replace**  
   Fermax uses **`deviceId/callAs`** as **`notify` tag** so replacements stack cleanly; use a stable **`tag`** (or documented replacement key) in `mobile_app` notifications to update or clear one logical “ringing” alert.

When you experiment, treat this doc as a **spec of the Duox behavior**, not as a guarantee that every field has a 1:1 equivalent in YAML.

---

## Re-decompiling the missing method

If `buildIncomingCallNotification` disappears after re-running jadx, recover it with:

```bash
jadx --show-bad-code --decompilation-mode restructure \
  --single-class com.fermax.blue.app.ui.viewmodels.NotificationViewModel \
  --single-class-output . \
  /path/to/Fermax_DuoxMe-*.apk
```

The recovered Java may need a small fix: initialize the `NotificationCompat.Builder` and tag prefix **before** conditional full-screen branches so `build()` is never called on an uninitialized builder (see comment in the patched `NotificationViewModel.java` in this repo’s `apk-decompiled/` tree).
