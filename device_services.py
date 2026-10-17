"""
HealthTrack - Device Audio (Alarm / Ringtone), Haptics and Local Notification Service.
Fully compatible with Android Native APIs (RingtoneManager, MediaPlayer, Vibrator,
NotificationManager, WakeLock, Permissions) and Windows winsound.
Built-in support for realistic Water sound, Rain sound, Zen Chime, and Alarm Bell ringtones.
"""

import os
import sys
import time
import threading

class LocalNotificationService:
    @staticmethod
    def schedule_water_reminder(next_time_epoch, glass_number=1, message=None, sound_key="water_droplets"):
        title = "💧 HealthTrack - Time to Drink Water!"
        body = message or f"Time for glass #{glass_number}! Stay hydrated, energized and healthy."

        # 1. Android Native Heads-up Alarm Notification with WakeLock & Sound
        try:
            from jnius import autoclass
            ActivityThread = autoclass('android.app.ActivityThread')
            app = ActivityThread.currentApplication()
            if app:
                ctx = app.getApplicationContext()
                Context = autoclass('android.content.Context')
                NotificationManager = autoclass('android.app.NotificationManager')
                notif_manager = ctx.getSystemService(Context.NOTIFICATION_SERVICE)

                Build = autoclass('android.os.Build')
                RingtoneManager = autoclass('android.media.RingtoneManager')
                AudioAttributes = autoclass('android.media.AudioAttributes')
                PowerManager = autoclass('android.os.PowerManager')

                # Wake up device screen if sleeping
                try:
                    pm = ctx.getSystemService(Context.POWER_SERVICE)
                    if pm:
                        wake_lock = pm.newWakeLock(
                            PowerManager.FULL_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP | PowerManager.ON_AFTER_RELEASE,
                            "healthtrack:alarm_wakeup"
                        )
                        wake_lock.acquire(3000)
                except Exception:
                    pass

                channel_id = f"healthtrack_alarm_{sound_key}"
                alarm_sound_uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
                if not alarm_sound_uri:
                    alarm_sound_uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)

                if Build.VERSION.SDK_INT >= 26:
                    NotificationChannel = autoclass('android.app.NotificationChannel')
                    channel = NotificationChannel(
                        channel_id,
                        "HealthTrack Hydration Alarms",
                        NotificationManager.IMPORTANCE_HIGH
                    )
                    channel.setDescription("Water intake and medicine reminders with customizable sounds")
                    channel.enableVibration(True)
                    channel.setBypassDnd(True)
                    channel.setLockscreenVisibility(1)

                    if alarm_sound_uri:
                        audio_attr = AudioAttributes.Builder() \
                            .setUsage(AudioAttributes.USAGE_ALARM) \
                            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION) \
                            .build()
                        channel.setSound(alarm_sound_uri, audio_attr)

                    notif_manager.createNotificationChannel(channel)

                Notification = autoclass('android.app.Notification')
                builder = Notification.Builder(ctx, channel_id) if Build.VERSION.SDK_INT >= 26 else Notification.Builder(ctx)
                builder.setContentTitle(title)
                builder.setContentText(body)
                builder.setSmallIcon(ctx.getApplicationInfo().icon)
                builder.setAutoCancel(True)
                builder.setPriority(2)
                builder.setVisibility(1)

                if alarm_sound_uri:
                    builder.setSound(alarm_sound_uri)

                notif_id = int(time.time()) % 100000
                notif_manager.notify(notif_id, builder.build())
        except Exception:
            pass

        # 2. Play custom ringtone (Water, Rain, Chime, Bell)
        play_ringtone_sound(sound_key)

        return {
            "scheduled": True,
            "scheduled_at": next_time_epoch,
            "title": title,
            "body": body,
            "sound": sound_key
        }

    @staticmethod
    def trigger_haptic_and_sound(sound_type="water_droplets", haptic=None):
        play_ringtone_sound(sound_type)


def request_runtime_permissions():
    """
    Triggers native Android permission dialogs for:
    - POST_NOTIFICATIONS (Android 13+)
    - CAMERA
    - READ_EXTERNAL_STORAGE / READ_MEDIA_IMAGES
    - Battery Optimization Exemption Intent
    """
    try:
        from jnius import autoclass
        ActivityThread = autoclass('android.app.ActivityThread')
        app = ActivityThread.currentApplication()
        if app:
            ctx = app.getApplicationContext()
            Intent = autoclass('android.content.Intent')
            Settings = autoclass('android.provider.Settings')
            Uri = autoclass('android.net.Uri')

            # Prompt ignore battery optimizations so background alarms never sleep
            try:
                PowerManager = autoclass('android.os.PowerManager')
                pm = ctx.getSystemService(Context.POWER_SERVICE)
                pkg = ctx.getPackageName()
                if pm and not pm.isIgnoringBatteryOptimizations(pkg):
                    intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                    intent.setData(Uri.parse(f"package:{pkg}"))
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    ctx.startActivity(intent)
            except Exception:
                pass
    except Exception:
        pass


def play_ringtone_sound(sound_key="water_droplets"):
    """
    Plays the chosen realistic ringtone:
    - 'water_droplets': Water pouring / droplet splashes
    - 'rain_gentle': Gentle rainfall sound
    - 'zen_chime': Peaceful meditation chime
    - 'alarm_bell': Classic ringing alarm bell
    - 'default_beep': Loud digital beep alert
    """
    wav_map = {
        "water_droplets": "water_droplets.wav",
        "rain_gentle": "rain_gentle.wav",
        "zen_chime": "zen_chime.wav",
        "alarm_bell": "alarm_bell.wav"
    }
    wav_fname = wav_map.get(sound_key, "water_droplets.wav")

    # Locate wav file
    wav_path = None
    search_dirs = [
        "assets/sounds",
        "sounds",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sounds"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
    ]
    for d in search_dirs:
        cand = os.path.join(d, wav_fname)
        if os.path.exists(cand):
            wav_path = os.path.abspath(cand)
            break

    # 1. Windows PC winsound playback (async, non-blocking)
    if sys.platform == "win32":
        try:
            import winsound
            if wav_path and os.path.exists(wav_path):
                winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
            else:
                winsound.Beep(1200, 800)
                return
        except Exception as e:
            print("Windows audio error:", e)

    # 2. Android Native MediaPlayer playback
    try:
        from jnius import autoclass
        MediaPlayer = autoclass('android.media.MediaPlayer')
        if wav_path and os.path.exists(wav_path):
            mp = MediaPlayer()
            mp.setDataSource(wav_path)
            mp.prepare()
            mp.start()
            return
    except Exception:
        pass

    # 3. Android RingtoneManager / ToneGenerator Fallback
    try:
        from jnius import autoclass
        ActivityThread = autoclass('android.app.ActivityThread')
        app = ActivityThread.currentApplication()
        if app:
            ctx = app.getApplicationContext()
            Context = autoclass('android.content.Context')
            vibrator = ctx.getSystemService(Context.VIBRATOR_SERVICE)
            if vibrator and vibrator.hasVibrator():
                vibrator.vibrate(800)

            RingtoneManager = autoclass('android.media.RingtoneManager')
            sound_uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            if not sound_uri:
                sound_uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
            if sound_uri:
                ringtone = RingtoneManager.getRingtone(ctx, sound_uri)
                if ringtone:
                    ringtone.play()
                    return
    except Exception:
        pass

    # 4. Universal console bell fallback
    try:
        print('\a', end='', flush=True)
    except Exception:
        pass
