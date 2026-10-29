package com.joshi.sleephome;

import android.accessibilityservice.AccessibilityService;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;

/**
 * Opens Home each time the screen turns off (sleep button, CEC, sleep timer).
 *
 * An app left in front at sleep can wake the Shield: if its process dies, Android restarts it as
 * the top activity, and its turnScreenOn flag turns the TV on. The stock launcher did this step
 * before it was disabled. Runs as an accessibility service because Android 11 lets a
 * system-bound service start an activity from the background, and the system keeps it running
 * and restarts it at boot.
 */
public class SleepHomeService extends AccessibilityService {
    private static final String TAG = "SleepHome";

    private final BroadcastReceiver screenOff = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            Intent home = new Intent(Intent.ACTION_MAIN)
                    .addCategory(Intent.CATEGORY_HOME)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            try {
                startActivity(home);
                Log.i(TAG, "screen off: Home opened");
            } catch (RuntimeException e) {
                Log.w(TAG, "screen off: could not open Home", e);
            }
        }
    };

    @Override
    protected void onServiceConnected() {
        // SCREEN_OFF is only delivered to receivers registered at run time.
        registerReceiver(screenOff, new IntentFilter(Intent.ACTION_SCREEN_OFF));
        Log.i(TAG, "service connected");
    }

    @Override
    public void onDestroy() {
        unregisterReceiver(screenOff);
        super.onDestroy();
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
    }

    @Override
    public void onInterrupt() {
    }
}
