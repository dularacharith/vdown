package com.vdown.app.ui.adapters;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.TextView;
import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;
import com.bumptech.glide.Glide;
import com.google.android.material.progressindicator.LinearProgressIndicator;
import com.vdown.app.R;
import com.vdown.app.data.DownloadItem;
import com.vdown.app.service.DownloadManager;
import com.vdown.app.utils.FormatUtils;
import java.util.ArrayList;
import java.util.List;

public class DownloadAdapter extends RecyclerView.Adapter<DownloadAdapter.ViewHolder> {
    private final List<DownloadItem> items = new ArrayList<>();

    public void updateList(List<DownloadItem> newItems) {
        this.items.clear();
        if (newItems != null) {
            this.items.addAll(newItems);
        }
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_download, parent, false);
        return new ViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ViewHolder holder, int position) {
        DownloadItem item = items.get(position);
        holder.tvTitle.setText(item.getTitle());

        String speedStr = FormatUtils.formatSpeed(item.getSpeedBytesPerSec());
        String etaStr = FormatUtils.formatEta(item.getEtaSeconds());
        holder.tvStatus.setText("Downloading: " + speedStr + " • " + etaStr);

        holder.progress.setProgress(item.getProgressPercent());

        String downloadedStr = FormatUtils.formatBytes(item.getDownloadedBytes());
        String totalStr = item.getTotalBytes() > 0 ? FormatUtils.formatBytes(item.getTotalBytes()) : "unknown";
        holder.tvSize.setText(downloadedStr + " / " + totalStr);
        holder.tvPercent.setText(item.getProgressPercent() + "%");

        if (item.getThumbnailUrl() != null && !item.getThumbnailUrl().isEmpty()) {
            Glide.with(holder.itemView.getContext())
                    .load(item.getThumbnailUrl())
                    .placeholder(item.isAudioOnly() ? R.drawable.ic_audio : R.drawable.ic_video)
                    .centerCrop()
                    .into(holder.ivIcon);
        } else {
            holder.ivIcon.setImageResource(item.isAudioOnly() ? R.drawable.ic_audio : R.drawable.ic_video);
        }

        holder.btnCancel.setOnClickListener(v -> {
            DownloadManager.getInstance(v.getContext()).cancelDownload(item.getId());
        });
    }

    @Override
    public int getItemCount() {
        return items.size();
    }

    static class ViewHolder extends RecyclerView.ViewHolder {
        ImageView ivIcon;
        TextView tvTitle, tvStatus, tvSize, tvPercent;
        LinearProgressIndicator progress;
        ImageButton btnCancel;

        public ViewHolder(@NonNull View itemView) {
            super(itemView);
            ivIcon = itemView.findViewById(R.id.iv_download_icon);
            tvTitle = itemView.findViewById(R.id.tv_download_title);
            tvStatus = itemView.findViewById(R.id.tv_download_status);
            tvSize = itemView.findViewById(R.id.tv_download_size);
            tvPercent = itemView.findViewById(R.id.tv_download_percent);
            progress = itemView.findViewById(R.id.progress_download);
            btnCancel = itemView.findViewById(R.id.btn_cancel_download);
        }
    }
}
