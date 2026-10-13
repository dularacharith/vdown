package com.vdown.app;

import android.app.Application;
import com.vdown.app.service.DownloadManager;
import com.vdown.app.utils.NotificationUtils;

public class VDownApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        NotificationUtils.createNotificationChannels(this);
        DownloadManager.getInstance(this).init();
    }
}
