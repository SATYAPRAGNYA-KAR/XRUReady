// frontend/unity-bridge/ConvaiIntegration.cs
// Integrates the Convai platform for patient avatar control.
// This bridges the Gemini-generated patient dialogue → Convai avatar lip-sync.
//
// Assumes Convai SDK is installed in the Unity project.
// See: https://docs.convai.com/api-docs/plugins-and-integrations/unity-plugin

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

// If using Convai SDK, these using statements will resolve:
// using Convai.Scripts.Runtime.Core;
// using Convai.Scripts.Runtime.LoggerSystem;

public class ConvaiIntegration : MonoBehaviour
{
    [Header("Convai Settings")]
    [Tooltip("Your Convai API key")]
    public string convaiApiKey = "";
    [Tooltip("The Convai character ID for your patient avatar")]
    public string patientCharacterId = "";

    [Header("Avatar")]
    public GameObject patientAvatarRoot;
    public Animator patientAnimator;

    [Header("Idle Animations")]
    public AnimationClip idleClip;
    public AnimationClip painGrimaceClip;
    public AnimationClip anxiousClip;
    public AnimationClip breathingHeavyClip;

    // Convai NPC component (set via Inspector after SDK import)
    // public ConvaiNPC convaiNPC;

    private AudioSource _patientAudioSource;
    private bool _isSpeaking = false;

    // ── Animator parameter hashes ─────────────────────────────────────
    private static readonly int IsSpeakingHash  = Animator.StringToHash("IsSpeaking");
    private static readonly int EmotionHash      = Animator.StringToHash("Emotion");
    private static readonly int PainLevelHash    = Animator.StringToHash("PainLevel");

    void Awake()
    {
        _patientAudioSource = patientAvatarRoot?.GetComponent<AudioSource>()
                              ?? patientAvatarRoot?.AddComponent<AudioSource>();
    }

    void Start()
    {
        // Set initial emotional state: anxious patient in pain
        SetEmotion(PatientEmotion.Anxious);
        SetPainLevel(7);  // 0-10 scale, James is at 7/10
    }

    // ── Play TTS audio on avatar + trigger lip sync ───────────────────
    public void PlayPatientAudio(string audioBase64)
    {
        if (string.IsNullOrEmpty(audioBase64)) return;
        StartCoroutine(PlayAudioCoroutine(audioBase64));
    }

    IEnumerator PlayAudioCoroutine(string base64Audio)
    {
        byte[] bytes = Convert.FromBase64String(base64Audio);
        string tempPath = System.IO.Path.Combine(Application.temporaryCachePath, "patient_tts.mp3");
        System.IO.File.WriteAllBytes(tempPath, bytes);

        using var uwr = UnityEngine.Networking.UnityWebRequestMultimedia.GetAudioClip(
            "file://" + tempPath, AudioType.MPEG
        );
        yield return uwr.SendWebRequest();

        if (uwr.result == UnityEngine.Networking.UnityWebRequest.Result.Success)
        {
            AudioClip clip = UnityEngine.Networking.DownloadHandlerAudioClip.GetContent(uwr);

            // -- If using Convai SDK, pass the audio to ConvaiNPC for lip sync:
            // convaiNPC?.PlayAudioClip(clip);

            // Fallback: direct audio playback
            _patientAudioSource.clip = clip;
            _patientAudioSource.Play();

            // Trigger speaking animation
            SetSpeaking(true);
            yield return new WaitForSeconds(clip.length);
            SetSpeaking(false);
        }
        else
        {
            Debug.LogError($"[Convai] Audio load failed: {uwr.error}");
        }
    }

    // ── Override: Send text directly to Convai for their TTS + lip sync ──
    // Use this instead of our TTS if you want Convai's own voice synthesis.
    public void SpeakViaConvai(string text)
    {
        // If using Convai SDK:
        // convaiNPC?.SendTextData(text);
        Debug.Log($"[Convai] Speaking via Convai NPC: {text}");
    }

    // ── Emotion & animation state ─────────────────────────────────────
    public void SetEmotion(PatientEmotion emotion)
    {
        if (patientAnimator == null) return;
        patientAnimator.SetInteger(EmotionHash, (int)emotion);
        Debug.Log($"[Convai] Patient emotion set to: {emotion}");
    }

    public void SetPainLevel(int level)
    {
        if (patientAnimator == null) return;
        patientAnimator.SetFloat(PainLevelHash, Mathf.Clamp01(level / 10f));
    }

    public void SetSpeaking(bool speaking)
    {
        _isSpeaking = speaking;
        patientAnimator?.SetBool(IsSpeakingHash, speaking);
    }

    // Trigger grimace when doctor asks about pain directly
    public void TriggerPainGrimace()
    {
        StartCoroutine(PainGrimaceCoroutine());
    }

    IEnumerator PainGrimaceCoroutine()
    {
        SetEmotion(PatientEmotion.InPain);
        yield return new WaitForSeconds(2.5f);
        SetEmotion(PatientEmotion.Anxious);
    }
}

public enum PatientEmotion
{
    Neutral  = 0,
    Anxious  = 1,
    InPain   = 2,
    Relieved = 3,
    Scared   = 4,
}
