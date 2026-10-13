package com.vdown.app.utils;

import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.util.Log;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.ShortBuffer;

/**
 * Boosts the audio gain of downloaded video or audio files (e.g. TikTok)
 * using native Android MediaExtractor, MediaCodec, and MediaMuxer.
 * Passes video track through untouched (0 re-encoding) and boosts audio PCM samples by +6dB to +8dB.
 */
public class AudioGainBooster {
    private static final String TAG = "AudioGainBooster";
    private static final long TIMEOUT_US = 10000;

    /**
     * Boosts audio in the given video file by the specified gain factor (e.g. 2.0f = +6dB, 2.5f = +8dB).
     * Returns true if successfully boosted and replaced, false otherwise.
     */
    public static boolean boostAudioInVideo(File inputFile, float gainFactor) {
        if (inputFile == null || !inputFile.exists() || inputFile.length() == 0) {
            return false;
        }

        File tempOutputFile = new File(inputFile.getParentFile(), "boosted_" + inputFile.getName());
        MediaExtractor extractor = new MediaExtractor();
        MediaMuxer muxer = null;
        MediaCodec decoder = null;
        MediaCodec encoder = null;

        try {
            extractor.setDataSource(inputFile.getAbsolutePath());
            int trackCount = extractor.getTrackCount();
            int audioTrackIndex = -1;
            int videoTrackIndex = -1;

            for (int i = 0; i < trackCount; i++) {
                MediaFormat format = extractor.getTrackFormat(i);
                String mime = format.getString(MediaFormat.KEY_MIME);
                if (mime != null) {
                    if (mime.startsWith("audio/") && audioTrackIndex == -1) {
                        audioTrackIndex = i;
                    } else if (mime.startsWith("video/") && videoTrackIndex == -1) {
                        videoTrackIndex = i;
                    }
                }
            }

            if (audioTrackIndex == -1) {
                extractor.release();
                return false;
            }

            muxer = new MediaMuxer(tempOutputFile.getAbsolutePath(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);

            int muxerVideoTrackIndex = -1;
            if (videoTrackIndex != -1) {
                MediaFormat videoFormat = extractor.getTrackFormat(videoTrackIndex);
                muxerVideoTrackIndex = muxer.addTrack(videoFormat);
            }

            // Set up audio decoder
            MediaFormat inputAudioFormat = extractor.getTrackFormat(audioTrackIndex);
            String audioMime = inputAudioFormat.getString(MediaFormat.KEY_MIME);
            int sampleRate = inputAudioFormat.getInteger(MediaFormat.KEY_SAMPLE_RATE);
            int channelCount = inputAudioFormat.getInteger(MediaFormat.KEY_CHANNEL_COUNT);

            decoder = MediaCodec.createDecoderByType(audioMime);
            decoder.configure(inputAudioFormat, null, null, 0);
            decoder.start();

            // Set up audio encoder (AAC)
            MediaFormat outputAudioFormat = MediaFormat.createAudioFormat("audio/mp4a-latm", sampleRate, channelCount);
            outputAudioFormat.setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC);
            outputAudioFormat.setInteger(MediaFormat.KEY_BIT_RATE, 192000); // 192 kbps high quality audio
            outputAudioFormat.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 32 * 1024);

            encoder = MediaCodec.createEncoderByType("audio/mp4a-latm");
            encoder.configure(outputAudioFormat, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            encoder.start();

            int muxerAudioTrackIndex = -1;
            boolean muxerStarted = false;

            // Video passthrough buffer
            ByteBuffer videoBuffer = ByteBuffer.allocateDirect(1024 * 1024);
            MediaCodec.BufferInfo videoBufferInfo = new MediaCodec.BufferInfo();

            // Copy video track if present
            if (videoTrackIndex != -1) {
                extractor.selectTrack(videoTrackIndex);
            }

            // Processing loop for audio decode -> gain boost -> encode -> mux
            extractor.selectTrack(audioTrackIndex);

            MediaCodec.BufferInfo decBufferInfo = new MediaCodec.BufferInfo();
            MediaCodec.BufferInfo encBufferInfo = new MediaCodec.BufferInfo();

            boolean extractorEos = false;
            boolean decoderEos = false;
            boolean encoderEos = false;

            // Loop to configure encoder track in muxer first
            while (!muxerStarted) {
                int encOutIndex = encoder.dequeueOutputBuffer(encBufferInfo, TIMEOUT_US);
                if (encOutIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    MediaFormat newFormat = encoder.getOutputFormat();
                    muxerAudioTrackIndex = muxer.addTrack(newFormat);
                    muxer.start();
                    muxerStarted = true;
                } else if (encOutIndex >= 0) {
                    encoder.releaseOutputBuffer(encOutIndex, false);
                } else {
                    // Feed decoder
                    if (!extractorEos) {
                        int decInIndex = decoder.dequeueInputBuffer(TIMEOUT_US);
                        if (decInIndex >= 0) {
                            ByteBuffer inBuf = decoder.getInputBuffer(decInIndex);
                            if (inBuf != null) {
                                int sampleSize = extractor.readSampleData(inBuf, 0);
                                if (sampleSize < 0) {
                                    decoder.queueInputBuffer(decInIndex, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                                    extractorEos = true;
                                } else {
                                    decoder.queueInputBuffer(decInIndex, 0, sampleSize, extractor.getSampleTime(), 0);
                                    extractor.advance();
                                }
                            }
                        }
                    }

                    // Feed encoder from decoder
                    int decOutIndex = decoder.dequeueOutputBuffer(decBufferInfo, TIMEOUT_US);
                    if (decOutIndex >= 0) {
                        ByteBuffer outBuf = decoder.getOutputBuffer(decOutIndex);
                        if (outBuf != null && decBufferInfo.size > 0) {
                            applyGainToPcm(outBuf, decBufferInfo, gainFactor);
                            feedEncoder(encoder, outBuf, decBufferInfo);
                        }
                        decoder.releaseOutputBuffer(decOutIndex, false);
                    }
                }
            }

            // Main processing loop
            while (!encoderEos) {
                // 1. Feed Decoder from Extractor
                if (!extractorEos) {
                    int decInIndex = decoder.dequeueInputBuffer(TIMEOUT_US);
                    if (decInIndex >= 0) {
                        ByteBuffer inBuf = decoder.getInputBuffer(decInIndex);
                        if (inBuf != null) {
                            int sampleSize = extractor.readSampleData(inBuf, 0);
                            if (sampleSize < 0) {
                                decoder.queueInputBuffer(decInIndex, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                                extractorEos = true;
                            } else {
                                decoder.queueInputBuffer(decInIndex, 0, sampleSize, extractor.getSampleTime(), 0);
                                extractor.advance();
                            }
                        }
                    }
                }

                // 2. Read PCM from Decoder, apply Gain, feed to Encoder
                if (!decoderEos) {
                    int decOutIndex = decoder.dequeueOutputBuffer(decBufferInfo, TIMEOUT_US);
                    if (decOutIndex >= 0) {
                        ByteBuffer outBuf = decoder.getOutputBuffer(decOutIndex);
                        if ((decBufferInfo.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) {
                            decoderEos = true;
                        }
                        if (outBuf != null && decBufferInfo.size > 0) {
                            applyGainToPcm(outBuf, decBufferInfo, gainFactor);
                            feedEncoder(encoder, outBuf, decBufferInfo);
                        }
                        decoder.releaseOutputBuffer(decOutIndex, false);
                    }
                }

                // 3. Read Encoded AAC from Encoder, write to Muxer
                int encOutIndex = encoder.dequeueOutputBuffer(encBufferInfo, TIMEOUT_US);
                if (encOutIndex >= 0) {
                    ByteBuffer encBuf = encoder.getOutputBuffer(encOutIndex);
                    if ((encBufferInfo.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) {
                        encoderEos = true;
                    }
                    if (encBuf != null && (encBufferInfo.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0 && encBufferInfo.size > 0) {
                        muxer.writeSampleData(muxerAudioTrackIndex, encBuf, encBufferInfo);
                    }
                    encoder.releaseOutputBuffer(encOutIndex, false);
                }
            }

            // 4. Pass through video samples directly
            if (videoTrackIndex != -1 && muxerVideoTrackIndex != -1) {
                extractor.unselectTrack(audioTrackIndex);
                extractor.seekTo(0, MediaExtractor.SEEK_TO_CLOSEST_SYNC);
                while (true) {
                    int sampleSize = extractor.readSampleData(videoBuffer, 0);
                    if (sampleSize < 0) break;
                    videoBufferInfo.offset = 0;
                    videoBufferInfo.size = sampleSize;
                    videoBufferInfo.presentationTimeUs = extractor.getSampleTime();
                    videoBufferInfo.flags = extractor.getSampleFlags();
                    muxer.writeSampleData(muxerVideoTrackIndex, videoBuffer, videoBufferInfo);
                    extractor.advance();
                }
            }

            // Cleanup & replace original file
            muxer.stop();
            muxer.release();
            muxer = null;

            extractor.release();
            if (decoder != null) { decoder.stop(); decoder.release(); decoder = null; }
            if (encoder != null) { encoder.stop(); encoder.release(); encoder = null; }

            if (tempOutputFile.exists() && tempOutputFile.length() > 0) {
                inputFile.delete();
                tempOutputFile.renameTo(inputFile);
                Log.d(TAG, "Audio successfully boosted for " + inputFile.getName());
                return true;
            }

        } catch (Exception e) {
            Log.e(TAG, "Error boosting audio: " + e.getMessage(), e);
            if (tempOutputFile.exists()) {
                tempOutputFile.delete();
            }
        } finally {
            try { if (decoder != null) decoder.release(); } catch (Exception ignored) {}
            try { if (encoder != null) encoder.release(); } catch (Exception ignored) {}
            try { if (muxer != null) muxer.release(); } catch (Exception ignored) {}
            try { extractor.release(); } catch (Exception ignored) {}
        }

        return false;
    }

    private static void applyGainToPcm(ByteBuffer buffer, MediaCodec.BufferInfo info, float gain) {
        buffer.position(info.offset);
        buffer.limit(info.offset + info.size);
        ShortBuffer shortBuf = buffer.order(ByteOrder.LITTLE_ENDIAN).asShortBuffer();
        int numSamples = shortBuf.remaining();
        for (int i = 0; i < numSamples; i++) {
            short sample = shortBuf.get(i);
            float boosted = sample * gain;
            // Soft clipping limiter
            if (boosted > 32767f) boosted = 32767f;
            else if (boosted < -32768f) boosted = -32768f;
            shortBuf.put(i, (short) boosted);
        }
        buffer.position(info.offset);
    }

    private static void feedEncoder(MediaCodec encoder, ByteBuffer pcmBuffer, MediaCodec.BufferInfo info) {
        int encInIndex = encoder.dequeueInputBuffer(TIMEOUT_US);
        if (encInIndex >= 0) {
            ByteBuffer inBuf = encoder.getInputBuffer(encInIndex);
            if (inBuf != null) {
                inBuf.clear();
                inBuf.put(pcmBuffer);
                encoder.queueInputBuffer(encInIndex, 0, info.size, info.presentationTimeUs, info.flags);
            }
        }
    }
}
