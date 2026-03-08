// frontend/unity-bridge/MetaQuestBridge.cs
// WebSocket bridge connecting Unity (Meta Quest) to the FastAPI backend.
// Attach this to a persistent GameObject in your scene.
// Requires: NativeWebSocket (https://github.com/endel/NativeWebSocket)

using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using NativeWebSocket;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

public class MetaQuestBridge : MonoBehaviour
{
    [Header("Server Configuration")]
    public string serverBaseUrl = "ws://localhost:8000";
    public string sessionId = "";

    [Header("References")]
    public AudioManager audioManager;
    public SessionController sessionController;
    public ConvaiIntegration convaiIntegration;

    private WebSocket _ws;
    private bool _isConnected = false;
    private Queue<string> _messageQueue = new Queue<string>();

    // ── Events ────────────────────────────────────────────────────────
    public static event Action<string, string> OnPatientResponse;    // (text, audioB64)
    public static event Action<string>         OnSTTResult;           // transcribed doctor text
    public static event Action<ToneData>       OnToneUpdate;          // tone score
    public static event Action<HPIUpdate>      OnHPIUpdate;           // HPI state
    public static event Action<EvaluationData> OnEvaluation;         // final evaluation
    public static event Action<string>         OnError;

    // ── Lifecycle ─────────────────────────────────────────────────────
    void Start()
    {
        if (!string.IsNullOrEmpty(sessionId))
            _ = ConnectWebSocket();
    }

    void Update()
    {
#if !UNITY_WEBGL || UNITY_EDITOR
        _ws?.DispatchMessageQueue();
#endif
        // Dequeue any cross-thread messages
        lock (_messageQueue)
        {
            while (_messageQueue.Count > 0)
                ProcessMessage(_messageQueue.Dequeue());
        }
    }

    async void OnDestroy()
    {
        if (_ws != null)
            await _ws.Close();
    }

    // ── Connect ───────────────────────────────────────────────────────
    public async System.Threading.Tasks.Task ConnectWebSocket()
    {
        string url = $"{serverBaseUrl}/ws/{sessionId}";
        Debug.Log($"[Bridge] Connecting to {url}");

        _ws = new WebSocket(url);

        _ws.OnOpen += () =>
        {
            _isConnected = true;
            Debug.Log("[Bridge] WebSocket connected");
            StartCoroutine(PingLoop());
        };

        _ws.OnMessage += (bytes) =>
        {
            string msg = Encoding.UTF8.GetString(bytes);
            lock (_messageQueue) { _messageQueue.Enqueue(msg); }
        };

        _ws.OnError += (err) =>
        {
            Debug.LogError($"[Bridge] WebSocket error: {err}");
            OnError?.Invoke(err);
        };

        _ws.OnClose += (code) =>
        {
            _isConnected = false;
            Debug.Log($"[Bridge] WebSocket closed: {code}");
        };

        await _ws.Connect();
    }

    // ── Send doctor text ─────────────────────────────────────────────
    public async void SendDoctorText(string text)
    {
        if (!_isConnected) return;
        var msg = JsonConvert.SerializeObject(new { type = "doctor_text", text });
        await _ws.SendText(msg);
        Debug.Log($"[Bridge] Sent doctor text: {text}");
    }

    // ── Send doctor audio (base64 WAV) ───────────────────────────────
    public async void SendDoctorAudio(string audioBase64, int sampleRate = 16000)
    {
        if (!_isConnected) return;
        var msg = JsonConvert.SerializeObject(new
        {
            type = "doctor_audio",
            audio_base64 = audioBase64,
            encoding = "LINEAR16",
            sample_rate = sampleRate,
        });
        await _ws.SendText(msg);
    }

    // ── Submit differential diagnosis ────────────────────────────────
    public async void SubmitDifferential(string differentialText)
    {
        if (!_isConnected) return;
        var msg = JsonConvert.SerializeObject(new
        {
            type = "submit_differential",
            text = differentialText,
        });
        await _ws.SendText(msg);
    }

    // ── Request evaluation ───────────────────────────────────────────
    public async void RequestEvaluation()
    {
        if (!_isConnected) return;
        await _ws.SendText(JsonConvert.SerializeObject(new { type = "request_evaluation" }));
    }

    // ── Ping loop ────────────────────────────────────────────────────
    IEnumerator PingLoop()
    {
        while (_isConnected)
        {
            yield return new WaitForSeconds(30f);
            _ = _ws.SendText(JsonConvert.SerializeObject(new { type = "ping" }));
        }
    }

    // ── Process incoming messages ─────────────────────────────────────
    void ProcessMessage(string raw)
    {
        try
        {
            JObject msg = JObject.Parse(raw);
            string type = msg["type"]?.ToString();

            switch (type)
            {
                case "patient_response":
                    string text = msg["text"]?.ToString();
                    string audio = msg["audio_base64"]?.ToString();
                    OnPatientResponse?.Invoke(text, audio);

                    // Trigger Convai avatar to play audio
                    convaiIntegration?.PlayPatientAudio(audio);

                    // Update tone display
                    if (msg["tone"] != null)
                    {
                        var tone = msg["tone"].ToObject<ToneData>();
                        OnToneUpdate?.Invoke(tone);
                        sessionController?.UpdateToneDisplay(tone);
                    }
                    break;

                case "stt_result":
                    string transcript = msg["text"]?.ToString();
                    OnSTTResult?.Invoke(transcript);
                    sessionController?.DisplayDoctorTranscript(transcript);
                    break;

                case "hpi_update":
                    var hpi = msg.ToObject<HPIUpdate>();
                    OnHPIUpdate?.Invoke(hpi);
                    sessionController?.UpdateHPIPanel(hpi);
                    break;

                case "differential_confirmed":
                    var diffs = msg["extracted_differentials"]?.ToObject<List<string>>();
                    sessionController?.OnDifferentialConfirmed(diffs);
                    break;

                case "evaluation":
                    var eval = msg["evaluation"]?.ToObject<EvaluationData>();
                    OnEvaluation?.Invoke(eval);
                    sessionController?.ShowEvaluationResults(eval);
                    break;

                case "error":
                    string err = msg["message"]?.ToString();
                    Debug.LogWarning($"[Bridge] Server error: {err}");
                    OnError?.Invoke(err);
                    break;

                case "pong":
                    // heartbeat ok
                    break;

                default:
                    Debug.Log($"[Bridge] Unknown message type: {type}");
                    break;
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"[Bridge] Message parse error: {e.Message}\nRaw: {raw}");
        }
    }
}

// ── Data transfer objects ────────────────────────────────────────────

[Serializable]
public class ToneData
{
    public string label;
    public float composite;
    public float empathy;
    public float warmth;
}

[Serializable]
public class HPIUpdate
{
    public Dictionary<string, object> hpi_state;
    public float coverage_percent;
    public List<string> missing_fields;
}

[Serializable]
public class EvaluationData
{
    public float overall_score;
    public string grade;
    public string detailed_feedback;
    public List<string> strengths;
    public List<string> areas_for_improvement;
}
