// PROTOTYPE ONLY: exercises the package in an exported release Player.
using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using Verve.WebView.Prototype;

public sealed class PrototypeRunner : MonoBehaviour
{
    [Serializable]
    private sealed class CreateResult { public bool ok; public uint handle; }

    [Serializable]
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
        var created = JsonUtility.FromJson<CreateResult>(proof.create);
        if (created == null || !created.ok) {
            Publish();
            return;
        }
        proof.open = VerveWebViewWeb.Request("open", created.handle, "{\"url\":\"https://example.invalid\"}");
        proof.dispose = VerveWebViewWeb.Request("dispose", created.handle);
        proof.disposedRequest = VerveWebViewWeb.Request("open", created.handle);
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
        var json = JsonUtility.ToJson(proof);
        Debug.Log("VERVE_PROTOTYPE_RESULT " + json);
        VerveWebViewWeb.PublishPrototypeResult(json);
    }
}
