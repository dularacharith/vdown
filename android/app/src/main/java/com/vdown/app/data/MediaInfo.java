package com.vdown.app.data;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class MediaInfo implements Serializable {
    private String id;
    private String url;
    private String title;
    private String author;
    private String platform;
    private String thumbnailUrl;
    private long durationSeconds;
    private List<MediaFormat> videoFormats = new ArrayList<>();
    private List<MediaFormat> audioFormats = new ArrayList<>();

    public MediaInfo() {}

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getUrl() {
        return url;
    }

    public void setUrl(String url) {
        this.url = url;
    }

    public String getTitle() {
        return title != null && !title.trim().isEmpty() ? title : "Media Download";
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getAuthor() {
        return author != null && !author.trim().isEmpty() ? author : "Unknown Creator";
    }

    public void setAuthor(String author) {
        this.author = author;
    }

    public String getPlatform() {
        return platform != null ? platform : "Web";
    }

    public void setPlatform(String platform) {
        this.platform = platform;
    }

    public String getThumbnailUrl() {
        return thumbnailUrl;
    }

    public void setThumbnailUrl(String thumbnailUrl) {
        this.thumbnailUrl = thumbnailUrl;
    }

    public long getDurationSeconds() {
        return durationSeconds;
    }

    public void setDurationSeconds(long durationSeconds) {
        this.durationSeconds = durationSeconds;
    }

    public List<MediaFormat> getVideoFormats() {
        return videoFormats;
    }

    public void setVideoFormats(List<MediaFormat> videoFormats) {
        this.videoFormats = videoFormats;
    }

    public List<MediaFormat> getAudioFormats() {
        return audioFormats;
    }

    public void setAudioFormats(List<MediaFormat> audioFormats) {
        this.audioFormats = audioFormats;
    }

    public void addVideoFormat(MediaFormat format) {
        this.videoFormats.add(format);
    }

    public void addAudioFormat(MediaFormat format) {
        this.audioFormats.add(format);
    }
}
