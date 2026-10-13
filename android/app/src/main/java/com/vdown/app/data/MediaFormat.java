package com.vdown.app.data;

import java.io.Serializable;

public class MediaFormat implements Serializable {
    private String formatId;
    private String label;
    private String extension;
    private String downloadUrl;
    private boolean isAudioOnly;
    private int qualityHeight;
    private int audioBitrateKbps;
    private long estimatedBytes;

    public MediaFormat() {}

    public MediaFormat(String formatId, String label, String extension, String downloadUrl, boolean isAudioOnly) {
        this.formatId = formatId;
        this.label = label;
        this.extension = extension;
        this.downloadUrl = downloadUrl;
        this.isAudioOnly = isAudioOnly;
    }

    public String getFormatId() {
        return formatId;
    }

    public void setFormatId(String formatId) {
        this.formatId = formatId;
    }

    public String getLabel() {
        return label;
    }

    public void setLabel(String label) {
        this.label = label;
    }

    public String getExtension() {
        return extension;
    }

    public void setExtension(String extension) {
        this.extension = extension;
    }

    public String getDownloadUrl() {
        return downloadUrl;
    }

    public void setDownloadUrl(String downloadUrl) {
        this.downloadUrl = downloadUrl;
    }

    public boolean isAudioOnly() {
        return isAudioOnly;
    }

    public void setAudioOnly(boolean audioOnly) {
        isAudioOnly = audioOnly;
    }

    public int getQualityHeight() {
        return qualityHeight;
    }

    public void setQualityHeight(int qualityHeight) {
        this.qualityHeight = qualityHeight;
    }

    public int getAudioBitrateKbps() {
        return audioBitrateKbps;
    }

    public void setAudioBitrateKbps(int audioBitrateKbps) {
        this.audioBitrateKbps = audioBitrateKbps;
    }

    public long getEstimatedBytes() {
        return estimatedBytes;
    }

    public void setEstimatedBytes(long estimatedBytes) {
        this.estimatedBytes = estimatedBytes;
    }
}
