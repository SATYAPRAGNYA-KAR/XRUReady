// frontend/unity-bridge/AudioManager.cs
// Handles microphone recording (doctor voice) and audio playback (patient TTS).
// Requires: OVRPlugin for Meta Quest microphone access.

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class AudioManager : MonoBehaviour
{
    [Header("Microphone Settings")]
    public int sampleRate = 16000;
    public int recordingBufferSeconds = 60;
    public float silenceThreshold = 0.02f;
    public float silenceDurationToStop = 1.5f;   // seconds of silence to auto-stop

    [Header("Audio Sources")]
    public AudioSource patientAudioSource;  // plays patient TTS

    private AudioClip _recordingClip;
    private bool _isRecording = false;
    private float _silenceTimer = 0f;
    private List<float> _recordedSamples = new List<float>();
    private MetaQuestBridge _bridge;

    void Start()
    {
        _bridge = FindObjectOfType<MetaQuestBridge>();

        if (Microphone.devices.Length == 0)
            Debug.LogWarning("[AudioManager] No microphone found!");

        if (patientAudioSource == null)
        {
            patientAudioSource = gameObject.AddComponent<AudioSource>();
            patientAudioSource.spatialBlend = 0.8f;  // slight 3D for XR immersion
            patientAudioSource.volume = 1.0f;
        }
    }

    // ── START RECORDING (Call when doctor presses the "Speak" button) ──
    public void StartRecording()
    {
        if (_isRecording) return;
        _isRecording = true;
        _recordedSamples.Clear();
        _silenceTimer = 0f;

        string mic = Microphone.devices.Length > 0 ? Microphone.devices[0] : null;
        _recordingClip = Microphone.Start(mic, true, recordingBufferSeconds, sampleRate);
        Debug.Log("[AudioManager] Recording started");

        StartCoroutine(MonitorSilence());
    }

    // ── STOP RECORDING & SEND ─────────────────────────────────────────
    public void StopRecordingAndSend()
    {
        if (!_isRecording) return;
        StopAllCoroutines();
        _isRecording = false;

        string mic = Microphone.devices.Length > 0 ? Microphone.devices[0] : null;
        int pos = Microphone.GetPosition(mic);
        Microphone.End(mic);

        // Extract samples up to current position
        float[] samples = new float[pos * _recordingClip.channels];
        _recordingClip.GetData(samples, 0);

        // Convert float PCM → Int16 bytes → Base64
        byte[] pcmBytes = FloatToPCM16(samples);
        string audioBase64 = Convert.ToBase64String(pcmBytes);

        Debug.Log($"[AudioManager] Sending audio: {pcmBytes.Length} bytes, {pos} samples");
        _bridge?.SendDoctorAudio(audioBase64, sampleRate);
    }

    // ── AUTO SILENCE DETECTION ────────────────────────────────────────
    IEnumerator MonitorSilence()
    {
        string mic = Microphone.devices.Length > 0 ? Microphone.devices[0] : null;
        int lastPos = 0;

        while (_isRecording)
        {
            yield return new WaitForSeconds(0.1f);
            int pos = Microphone.GetPosition(mic);
            if (pos == lastPos) continue;

            int samplesToRead = pos - lastPos;
            if (samplesToRead < 0) samplesToRead += _recordingClip.samples;

            float[] temp = new float[samplesToRead];
            _recordingClip.GetData(temp, lastPos % _recordingClip.samples);
            lastPos = pos;

            float rms = GetRMS(temp);
            if (rms < silenceThreshold)
            {
                _silenceTimer += 0.1f;
                if (_silenceTimer >= silenceDurationToStop)
                {
                    Debug.Log("[AudioManager] Silence detected — auto-stopping recording");
                    StopRecordingAndSend();
                    yield break;
                }
            }
            else
            {
                _silenceTimer = 0f;
            }
        }
    }

    // ── PLAY PATIENT AUDIO ────────────────────────────────────────────
    public void PlayPatientAudio(string audioBase64)
    {
        if (string.IsNullOrEmpty(audioBase64)) return;
        StartCoroutine(PlayBase64Audio(audioBase64));
    }

    IEnumerator PlayBase64Audio(string base64Audio)
    {
        byte[] bytes = Convert.FromBase64String(base64Audio);
        // MP3 from Google TTS — decode using Unity's built-in or NAudio
        // Unity can play WAV natively; for MP3 we use AudioType.MPEG
        // Use a temp file for simplicity (in a real build, use UnityWebRequest from memory)
        string tempPath = System.IO.Path.Combine(Application.temporaryCachePath, "patient_speech.mp3");
        System.IO.File.WriteAllBytes(tempPath, bytes);

        using var uwr = UnityEngine.Networking.UnityWebRequestMultimedia.GetAudioClip(
            "file://" + tempPath, AudioType.MPEG
        );
        yield return uwr.SendWebRequest();

        if (uwr.result == UnityEngine.Networking.UnityWebRequest.Result.Success)
        {
            AudioClip clip = UnityEngine.Networking.DownloadHandlerAudioClip.GetContent(uwr);
            patientAudioSource.clip = clip;
            patientAudioSource.Play();
            Debug.Log("[AudioManager] Playing patient TTS audio");
        }
        else
        {
            Debug.LogError($"[AudioManager] Failed to load TTS audio: {uwr.error}");
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────
    float GetRMS(float[] samples)
    {
        float sum = 0f;
        foreach (var s in samples) sum += s * s;
        return Mathf.Sqrt(sum / samples.Length);
    }

    byte[] FloatToPCM16(float[] samples)
    {
        byte[] bytes = new byte[samples.Length * 2];
        for (int i = 0; i < samples.Length; i++)
        {
            short val = (short)(Mathf.Clamp(samples[i], -1f, 1f) * short.MaxValue);
            bytes[i * 2]     = (byte)(val & 0xFF);
            bytes[i * 2 + 1] = (byte)((val >> 8) & 0xFF);
        }
        return bytes;
    }
}
