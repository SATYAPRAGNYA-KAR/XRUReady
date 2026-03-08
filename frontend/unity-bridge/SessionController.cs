// frontend/unity-bridge/SessionController.cs
// Controls the XR training session lifecycle, UI overlays,
// and HPI/tone display panels visible to the doctor in the headset.
//
// Designed for Meta Quest 3 using the OVR SDK.
// Attach to a persistent scene controller GameObject.

using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class SessionController : MonoBehaviour
{
    [Header("Server Config")]
    public string backendUrl = "http://localhost:8000";

    [Header("Session")]
    public string traineeId = "trainee_001";
    public string traineeName = "Dr. Trainee";

    [Header("UI - Doctor HUD (visible inside headset)")]
    public GameObject hudPanel;
    public TextMeshProUGUI phaseLabel;
    public TextMeshProUGUI hpiCoverageText;
    public TextMeshProUGUI missingFieldsText;
    public Slider hpiProgressBar;

    [Header("UI - Tone Indicator")]
    public GameObject tonePanel;
    public TextMeshProUGUI toneLabelText;
    public Image toneColorIndicator;
    public TextMeshProUGUI compositeScoreText;

    [Header("UI - Transcript")]
    public TextMeshProUGUI doctorTranscriptText;
    public TextMeshProUGUI patientResponseText;
    public ScrollRect transcriptScrollRect;

    [Header("UI - Evaluation (post-session)")]
    public GameObject evaluationPanel;
    public TextMeshProUGUI overallScoreText;
    public TextMeshProUGUI gradeText;
    public TextMeshProUGUI feedbackText;
    public TextMeshProUGUI strengthsText;
    public TextMeshProUGUI improvementsText;

    [Header("Buttons")]
    public Button startButton;
    public Button speakButton;
    public Button stopSpeakingButton;
    public Button submitDifferentialButton;
    public Button requestEvaluationButton;

    [Header("Differential Diagnosis")]
    public TMP_InputField differentialInputField;

    [Header("Audio")]
    public AudioManager audioManager;
    public MetaQuestBridge bridge;

    private string _sessionId = "";
    private bool _sessionStarted = false;
    private List<string> _transcriptLines = new List<string>();

    // ── Tone colors ───────────────────────────────────────────────────
    private static readonly Dictionary<string, Color> ToneColors = new Dictionary<string, Color>
    {
        { "empathetic",   new Color(0.22f, 0.78f, 0.42f) },  // green
        { "reassuring",   new Color(0.12f, 0.65f, 0.90f) },  // blue
        { "neutral",      new Color(0.85f, 0.85f, 0.85f) },  // light grey
        { "cold",         new Color(0.95f, 0.55f, 0.15f) },  // orange
        { "abrupt",       new Color(0.95f, 0.30f, 0.30f) },  // red
        { "dismissive",   new Color(0.80f, 0.10f, 0.10f) },  // dark red
    };

    // ── Lifecycle ─────────────────────────────────────────────────────
    void Start()
    {
        evaluationPanel?.SetActive(false);

        // Wire buttons
        startButton?.onClick.AddListener(OnStartSession);
        speakButton?.onClick.AddListener(() => audioManager?.StartRecording());
        stopSpeakingButton?.onClick.AddListener(() => audioManager?.StopRecordingAndSend());
        submitDifferentialButton?.onClick.AddListener(OnSubmitDifferential);
        requestEvaluationButton?.onClick.AddListener(OnRequestEvaluation);
    }

    // ── Start session via REST then connect WebSocket ─────────────────
    async void OnStartSession()
    {
        startButton.interactable = false;
        Debug.Log("[SessionController] Starting session...");

        string url = $"{backendUrl}/session/start";
        var payload = new { trainee_id = traineeId, trainee_name = traineeName };
        string body = Newtonsoft.Json.JsonConvert.SerializeObject(payload);

        using var req = new UnityEngine.Networking.UnityWebRequest(url, "POST");
        byte[] bodyRaw = System.Text.Encoding.UTF8.GetBytes(body);
        req.uploadHandler = new UnityEngine.Networking.UploadHandlerRaw(bodyRaw);
        req.downloadHandler = new UnityEngine.Networking.DownloadHandlerBuffer();
        req.SetRequestHeader("Content-Type", "application/json");

        await req.SendWebRequest();

        if (req.result == UnityEngine.Networking.UnityWebRequest.Result.Success)
        {
            var resp = Newtonsoft.Json.JsonConvert.DeserializeAnonymousType(
                req.downloadHandler.text,
                new { session_id = "", opening_patient_statement = "", opening_audio_base64 = "" }
            );

            _sessionId = resp.session_id;
            _sessionStarted = true;

            // Connect WebSocket
            bridge.sessionId = _sessionId;
            await bridge.ConnectWebSocket();

            // Display opening patient statement
            AppendToTranscript("PATIENT", resp.opening_patient_statement);
            patientResponseText.text = resp.opening_patient_statement;

            // Play TTS audio
            if (!string.IsNullOrEmpty(resp.opening_audio_base64))
                audioManager?.PlayPatientAudio(resp.opening_audio_base64);

            phaseLabel.text = "Phase: Introduction";
            Debug.Log($"[SessionController] Session started: {_sessionId}");
        }
        else
        {
            Debug.LogError($"[SessionController] Failed to start session: {req.error}");
            startButton.interactable = true;
        }
    }

    // ── Submit differential ───────────────────────────────────────────
    void OnSubmitDifferential()
    {
        string text = differentialInputField?.text ?? "";
        if (string.IsNullOrEmpty(text))
        {
            Debug.LogWarning("[SessionController] Differential text is empty");
            return;
        }
        bridge?.SubmitDifferential(text);
        submitDifferentialButton.interactable = false;
        requestEvaluationButton.interactable = true;
    }

    void OnRequestEvaluation()
    {
        bridge?.RequestEvaluation();
        requestEvaluationButton.interactable = false;
    }

    // ── UI update callbacks ────────────────────────────────────────────
    public void UpdateToneDisplay(ToneData tone)
    {
        if (toneLabelText)
            toneLabelText.text = $"Tone: {tone.label.ToUpper()}";

        if (compositeScoreText)
            compositeScoreText.text = $"Score: {tone.composite:F1}/10";

        if (toneColorIndicator && ToneColors.TryGetValue(tone.label.ToLower(), out Color c))
            toneColorIndicator.color = c;
    }

    public void UpdateHPIPanel(HPIUpdate hpi)
    {
        if (hpiProgressBar)
            hpiProgressBar.value = hpi.coverage_percent / 100f;

        if (hpiCoverageText)
            hpiCoverageText.text = $"HPI Coverage: {hpi.coverage_percent:F0}%";

        if (missingFieldsText && hpi.missing_fields != null)
            missingFieldsText.text = "Missing: " + string.Join(", ", hpi.missing_fields);
    }

    public void DisplayDoctorTranscript(string text)
    {
        if (doctorTranscriptText)
            doctorTranscriptText.text = $"You: {text}";
        AppendToTranscript("DOCTOR", text);
    }

    public void OnDifferentialConfirmed(List<string> differentials)
    {
        Debug.Log("[SessionController] Differential confirmed: " + string.Join(", ", differentials));
    }

    public void ShowEvaluationResults(EvaluationData eval)
    {
        evaluationPanel?.SetActive(true);

        if (overallScoreText) overallScoreText.text = $"{eval.overall_score:F0}/100";
        if (gradeText) gradeText.text = $"Grade: {eval.grade}";
        if (feedbackText) feedbackText.text = eval.detailed_feedback;

        if (strengthsText && eval.strengths != null)
            strengthsText.text = "Strengths:\n• " + string.Join("\n• ", eval.strengths);

        if (improvementsText && eval.areas_for_improvement != null)
            improvementsText.text = "Improve:\n• " + string.Join("\n• ", eval.areas_for_improvement);
    }

    // ── Helpers ───────────────────────────────────────────────────────
    void AppendToTranscript(string speaker, string text)
    {
        _transcriptLines.Add($"[{speaker}] {text}");
        if (_transcriptLines.Count > 100)
            _transcriptLines.RemoveAt(0);

        // Update scroll view if available
        if (transcriptScrollRect != null)
        {
            var content = transcriptScrollRect.content.GetComponent<TextMeshProUGUI>();
            if (content) content.text = string.Join("\n\n", _transcriptLines);
            Canvas.ForceUpdateCanvases();
            transcriptScrollRect.verticalNormalizedPosition = 0f;
        }
    }
}
