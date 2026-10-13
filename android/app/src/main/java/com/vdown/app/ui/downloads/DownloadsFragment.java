package com.vdown.app.ui.downloads;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import com.vdown.app.R;
import com.vdown.app.data.DownloadItem;
import com.vdown.app.service.DownloadManager;
import com.vdown.app.ui.adapters.DownloadAdapter;
import java.util.List;

public class DownloadsFragment extends Fragment implements DownloadManager.DownloadListener {

    private RecyclerView recyclerDownloads;
    private View layoutEmpty;
    private DownloadAdapter adapter;

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container, @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_downloads, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        recyclerDownloads = view.findViewById(R.id.recycler_downloads);
        layoutEmpty = view.findViewById(R.id.layout_empty_downloads);

        adapter = new DownloadAdapter();
        recyclerDownloads.setLayoutManager(new LinearLayoutManager(requireContext()));
        recyclerDownloads.setAdapter(adapter);

        DownloadManager.getInstance(requireContext()).addListener(this);
        refreshData();
    }

    @Override
    public void onResume() {
        super.onResume();
        refreshData();
    }

    private void refreshData() {
        if (getContext() == null) return;
        List<DownloadItem> active = DownloadManager.getInstance(requireContext()).getActiveDownloads();
        adapter.updateList(active);

        if (active.isEmpty()) {
            layoutEmpty.setVisibility(View.VISIBLE);
            recyclerDownloads.setVisibility(View.GONE);
        } else {
            layoutEmpty.setVisibility(View.GONE);
            recyclerDownloads.setVisibility(View.VISIBLE);
        }
    }

    @Override
    public void onDownloadProgress(DownloadItem item) {
        refreshData();
    }

    @Override
    public void onDownloadCompleted(DownloadItem item) {
        refreshData();
    }

    @Override
    public void onDownloadFailed(DownloadItem item, String error) {
        refreshData();
    }

    @Override
    public void onDownloadListChanged() {
        refreshData();
    }

    @Override
    public void onDestroyView() {
        if (getContext() != null) {
            DownloadManager.getInstance(requireContext()).removeListener(this);
        }
        super.onDestroyView();
    }
}
