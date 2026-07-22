// PROTOTYPE ONLY: exercises the package in an exported release Player.
using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using Verve.WebView.Prototype;

public sealed class PrototypeRunner : MonoBehaviour
{
    private sealed class ProofResult
    {
        public string engine = "unity";
        public string init;
        public string create;
        public string open;
        public string dispose;
        public string disposedRequest;
        public int lateCompletionEvents;
        public string trap;
    }

    private readonly List<string> events = new List<string>();
    private readonly ProofResult proof = new ProofResult();

    private void Start()
    {
        var page = new Uri(Application.absoluteURL);
        var wasm = new Uri(page, "VerveWebViewCore/verve_webview_core_bg.wasm").AbsoluteUri;
        VerveWebViewWeb.Initialize(wasm, OnInitialized, value => events.Add(value));
    }

    private void OnInitialized(string value)
    {
        proof.init = value;
        proof.create = VerveWebViewWeb.CreateInstance();
        if (!TryReadHandle(proof.create, out var handle)) {
            Publish();
            return;
        }
        proof.open = VerveWebViewWeb.Request("open", handle, "{\"url\":\"https://example.invalid\"}");
        proof.dispose = VerveWebViewWeb.Request("dispose", handle);
        proof.disposedRequest = VerveWebViewWeb.Request("open", handle);
        StartCoroutine(FinishAfterMicrotasks());
    }

    private IEnumerator FinishAfterMicrotasks()
    {
        yield return null;
        yield return null;
        proof.lateCompletionEvents = events.Count;
        proof.trap = VerveWebViewWeb.PrototypeTrap();
        Publish();
    }

    private void Publish()
    {
        var json = "{\"engine\":\"unity\""
            + ",\"init\":" + Quote(proof.init)
            + ",\"create\":" + Quote(proof.create)
            + ",\"open\":" + Quote(proof.open)
            + ",\"dispose\":" + Quote(proof.dispose)
            + ",\"disposedRequest\":" + Quote(proof.disposedRequest)
            + ",\"lateCompletionEvents\":" + proof.lateCompletionEvents
            + ",\"trap\":" + Quote(proof.trap)
            + "}";
        Debug.Log("VERVE_PROTOTYPE_RESULT " + json);
        VerveWebViewWeb.PublishPrototypeResult(json);
    }

    private static bool TryReadHandle(string json, out uint handle)
    {
        handle = 0;
        if (string.IsNullOrEmpty(json) || !json.Contains("\"ok\":true")) return false;
        const string marker = "\"handle\":";
        var start = json.IndexOf(marker, StringComparison.Ordinal);
        if (start < 0) return false;
        start += marker.Length;
        var end = start;
        while (end < json.Length && char.IsDigit(json[end])) end++;
        return uint.TryParse(json.Substring(start, end - start), out handle);
    }

    private static string Quote(string value)
    {
        if (value == null) return "null";
        return "\"" + value
            .Replace("\\", "\\\\")
            .Replace("\"", "\\\"")
            .Replace("\r", "\\r")
            .Replace("\n", "\\n") + "\"";
    }
}
