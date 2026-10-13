package com.vdown.app.ui.adapters;

import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.TextView;
import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;
import com.google.android.material.button.MaterialButton;
import com.vdown.app.R;
import com.vdown.app.ui.player.PlayerActivity;
import com.vdown.app.utils.FileUtils;
import com.vdown.app.utils.FormatUtils;
import java.io.File;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class LibraryAdapter extends RecyclerView.Adapter<LibraryAdapter.ViewHolder> {
    private final List<File> files = new ArrayList<>();
    private final SimpleDateFormat dateFormat = new SimpleDateFormat("MMM dd, yyyy", Locale.getDefault());
    private final Runnable onItemDeletedCallback;

    public LibraryAdapter(Runnable onItemDeletedCallback) {
        this.onItemDeletedCallback = onItemDeletedCallback;
    }

    public void updateList(List<File> newFiles) {
        this.files.clear();
        if (newFiles != null) {
            this.files.addAll(newFiles);
        }
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_library, parent, false);
        return new ViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ViewHolder holder, int position) {
        File file = files.get(position);
        Context context = holder.itemView.getContext();

        String name = file.getName();
        holder.tvTitle.setText(name);

        String ext = "";
        if (name.contains(".")) {
            ext = name.substring(name.lastIndexOf('.') + 1).toUpperCase(Locale.US);
        }

        boolean isAudio = ext.equals("MP3") || ext.equals("FLAC") || ext.equals("M4A") || ext.equals("WAV") || ext.equals("OPUS");
        holder.ivIcon.setImageResource(isAudio ? R.drawable.ic_audio : R.drawable.ic_video);

        String sizeStr = FormatUtils.formatBytes(file.length());
        String dateStr = dateFormat.format(new Date(file.lastModified()));
        holder.tvDetails.setText(ext + " • " + sizeStr + " • " + dateStr);

        holder.btnPlay.setOnClickListener(v -> {
            Intent intent = new Intent(context, PlayerActivity.class);
            intent.putExtra(PlayerActivity.EXTRA_FILE_PATH, file.getAbsolutePath());
            intent.putExtra(PlayerActivity.EXTRA_MEDIA_TITLE, file.getName());
            intent.putExtra(PlayerActivity.EXTRA_IS_AUDIO, isAudio);
            context.startActivity(intent);
        });

        holder.btnShare.setOnClickListener(v -> {
            FileUtils.shareFile(context, file);
        });

        holder.btnDelete.setOnClickListener(v -> {
            new AlertDialog.Builder(context)
                    .setTitle(R.string.confirm_delete)
                    .setMessage("Are you sure you want to delete \"" + file.getName() + "\"?")
                    .setPositiveButton(R.string.btn_delete, (dialog, which) -> {
                        if (file.delete()) {
                            files.remove(position);
                            notifyItemRemoved(position);
                            notifyItemRangeChanged(position, files.size());
                            if (onItemDeletedCallback != null) {
                                onItemDeletedCallback.run();
                            }
                        }
                    })
                    .setNegativeButton(android.R.string.cancel, null)
                    .show();
        });
    }

    @Override
    public int getItemCount() {
        return files.size();
    }

    static class ViewHolder extends RecyclerView.ViewHolder {
        ImageView ivIcon;
        TextView tvTitle, tvDetails;
        MaterialButton btnPlay, btnShare;
        ImageButton btnDelete;

        public ViewHolder(@NonNull View itemView) {
            super(itemView);
            ivIcon = itemView.findViewById(R.id.iv_library_icon);
            tvTitle = itemView.findViewById(R.id.tv_library_title);
            tvDetails = itemView.findViewById(R.id.tv_library_details);
            btnPlay = itemView.findViewById(R.id.btn_library_play);
            btnShare = itemView.findViewById(R.id.btn_library_share);
            btnDelete = itemView.findViewById(R.id.btn_library_delete);
        }
    }
}
