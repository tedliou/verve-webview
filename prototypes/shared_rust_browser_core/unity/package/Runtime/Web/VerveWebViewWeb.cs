// PROTOTYPE ONLY: Unity transport for the independent browser Core.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using AOT;
using UnityEngine.Scripting;

namespace Verve.WebView.Prototype
{
    [Preserve]
    public static class VerveWebViewWeb
    {
        private delegate void NativeCallback(int requestId, IntPtr json);

        private static readonly NativeCallback InitCallbackRoot = OnInitialized;
        private static readonly NativeCallback EventCallbackRoot = OnEvent;
        private static readonly Dictionary<int, Action<string>> Pending = new Dictionary<int, Action<string>>();
        private static Action<string> eventSink;
        private static int nextRequestId = 1;

        [DllImport("__Internal")]
        private static extern void VerveWebView_Initialize(int requestId, string wasmUrl, NativeCallback callback);

        [DllImport("__Internal")]
        private static extern void VerveWebView_SetEventSink(NativeCallback callback);

        [DllImport("__Internal")]
        private static extern IntPtr VerveWebView_CreateInstance();

        [DllImport("__Internal")]
        private static extern IntPtr VerveWebView_Request(string operation, uint handle, string payloadJson);

        [DllImport("__Internal")]
        private static extern IntPtr VerveWebView_PrototypeTrap();

        [DllImport("__Internal")]
        private static extern void VerveWebView_Free(IntPtr value);

        public static void Initialize(string wasmUrl, Action<string> completed, Action<string> onEvent)
        {
            eventSink = onEvent;
#if UNITY_WEBGL && !UNITY_EDITOR
            var requestId = nextRequestId++;
            Pending.Add(requestId, completed);
            VerveWebView_SetEventSink(EventCallbackRoot);
            VerveWebView_Initialize(requestId, wasmUrl, InitCallbackRoot);
#else
            completed("{\"ok\":false,\"code\":\"unsupported_prototype_host\"}");
#endif
        }

        public static string CreateInstance()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            return TakeString(VerveWebView_CreateInstance());
#else
            return "{\"ok\":false,\"code\":\"unsupported_prototype_host\"}";
#endif
        }

        public static string Request(string operation, uint handle, string payloadJson = "{}")
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            return TakeString(VerveWebView_Request(operation, handle, payloadJson));
#else
            return "{\"ok\":false,\"code\":\"unsupported_prototype_host\"}";
#endif
        }

        public static string PrototypeTrap()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            return TakeString(VerveWebView_PrototypeTrap());
#else
            return "{\"ok\":false,\"code\":\"unsupported_prototype_host\"}";
#endif
        }

        public static void PublishPrototypeResult(string json)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            VerveWebView_PrototypePublish(json);
#endif
        }

        [DllImport("__Internal")]
        private static extern void VerveWebView_PrototypePublish(string json);

        [Preserve]
        [MonoPInvokeCallback(typeof(NativeCallback))]
        private static void OnInitialized(int requestId, IntPtr json)
        {
            var message = Marshal.PtrToStringAnsi(json) ?? "";
            VerveWebView_Free(json);
            if (!Pending.TryGetValue(requestId, out var callback)) return;
            Pending.Remove(requestId);
            callback(message);
        }

        [Preserve]
        [MonoPInvokeCallback(typeof(NativeCallback))]
        private static void OnEvent(int requestId, IntPtr json)
        {
            var message = Marshal.PtrToStringAnsi(json) ?? "";
            VerveWebView_Free(json);
            eventSink?.Invoke(message);
        }

        private static string TakeString(IntPtr value)
        {
            var message = Marshal.PtrToStringAnsi(value) ?? "";
            VerveWebView_Free(value);
            return message;
        }
    }
}
