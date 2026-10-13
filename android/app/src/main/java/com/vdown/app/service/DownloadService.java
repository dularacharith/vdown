package com.vdown.app.service;

import android.app.Notification;
import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import androidx.annotation.Nullable;
import com.vdown.app.data.DownloadItem;
import com.vdown.app.utils.NotificationUtils;
import java.util.List;

public class DownloadService extends Service implements DownloadManager.DownloadListener {

    @Override
    public void onCreate() {
        super.onCreate();
        DownloadManager.getInstance(this).addListener(this);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        updateForegroundNotification();
        return START_NOT_STICKY;
    }

    private void updateForegroundNotification() {
        List<DownloadItem> active = DownloadManager.getInstance(this).getActiveDownloads();
        if (active.isEmpty()) {
            stopForeground(true);
            stopSelf();
            return;
        }

        DownloadItem current = active.get(0);
        Notification notification = NotificationUtils.buildProgressNotification(this, current);
        startForeground(NotificationUtils.FOREGROUND_NOTIFICATION_ID, notification);
    }

    @Override
    public void onDownloadProgress(DownloadItem item) {
        updateForegroundNotification();
    }

    @Override
    public void onDownloadCompleted(DownloadItem item) {
        NotificationUtils.showCompleteNotification(this, (int) System.currentTimeMillis(), item.getTitle());
        updateForegroundNotification();
    }

    @Override
    public void onDownloadFailed(DownloadItem item, String error) {
        updateForegroundNotification();
    }

    @Override
    public void onDownloadListChanged() {
        updateForegroundNotification();
    }

    @Override
    public void onDestroy() {
        DownloadManager.getInstance(this).removeListener(this);
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
