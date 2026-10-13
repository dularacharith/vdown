package com.vdown.app.data;

import java.io.Serializable;

public class DownloadItem implements Serializable {
    public enum Status {
        PENDING,
        DOWNLOADING,
        COMPLETED,
        FAILED,
        PAUSED,
        CANCELED
    }

    private String id;
    private String title;
    private String sourceUrl;
    private String downloadUrl;
    private String destinationPath;
    private String thumbnailUrl;
    private String extension;
    private boolean isAudioOnly;
    private String qualityLabel;
    private Status status = Status.PENDING;
    private int progressPercent = 0;
    private long downloadedBytes = 0;
    private long totalBytes = 0;
    private double speedBytesPerSec = 0;
    private long etaSeconds = 0;
    private long timestamp = System.currentTimeMillis();
    private String errorMessage;

    public DownloadItem() {}

    public DownloadItem(String id, String title, String sourceUrl, String downloadUrl, String extension, boolean isAudioOnly) {
        this.id = id;
        this.title = title;
        this.sourceUrl = sourceUrl;
        this.downloadUrl = downloadUrl;
        this.extension = extension;
        this.isAudioOnly = isAudioOnly;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getTitle() {
        return title != null ? title : "Media";
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getSourceUrl() {
        return sourceUrl;
    }

    public void setSourceUrl(String sourceUrl) {
        this.sourceUrl = sourceUrl;
    }

    public String getDownloadUrl() {
        return downloadUrl;
    }

    public void setDownloadUrl(String downloadUrl) {
        this.downloadUrl = downloadUrl;
    }

    public String getDestinationPath() {
        return destinationPath;
    }

    public void setDestinationPath(String destinationPath) {
        this.destinationPath = destinationPath;
    }

    public String getThumbnailUrl() {
        return thumbnailUrl;
    }

    public void setThumbnailUrl(String thumbnailUrl) {
        this.thumbnailUrl = thumbnailUrl;
    }

    public String getExtension() {
        return extension != null ? extension : (isAudioOnly ? "mp3" : "mp4");
    }

    public void setExtension(String extension) {
        this.extension = extension;
    }

    public boolean isAudioOnly() {
        return isAudioOnly;
    }

    public void setAudioOnly(boolean audioOnly) {
        isAudioOnly = audioOnly;
    }

    public String getQualityLabel() {
        return qualityLabel;
    }

    public void setQualityLabel(String qualityLabel) {
        this.qualityLabel = qualityLabel;
    }

    public Status getStatus() {
        return status;
    }

    public void setStatus(Status status) {
        this.status = status;
    }

    public int getProgressPercent() {
        return progressPercent;
    }

    public void setProgressPercent(int progressPercent) {
        this.progressPercent = progressPercent;
    }

    public long getDownloadedBytes() {
        return downloadedBytes;
    }

    public void setDownloadedBytes(long downloadedBytes) {
        this.downloadedBytes = downloadedBytes;
    }

    public long getTotalBytes() {
        return totalBytes;
    }

    public void setTotalBytes(long totalBytes) {
        this.totalBytes = totalBytes;
    }

    public double getSpeedBytesPerSec() {
        return speedBytesPerSec;
    }

    public void setSpeedBytesPerSec(double speedBytesPerSec) {
        this.speedBytesPerSec = speedBytesPerSec;
    }

    public long getEtaSeconds() {
        return etaSeconds;
    }

    public void setEtaSeconds(long etaSeconds) {
        this.etaSeconds = etaSeconds;
    }

    public long getTimestamp() {
        return timestamp;
    }

    public void setTimestamp(long timestamp) {
        this.timestamp = timestamp;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }
}
