#nullable enable
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;

namespace Verve.WebView
{
    public sealed class WebView
    {
        private readonly IWebViewBridge bridge;
        private readonly IUnityMainThreadScheduler mainThread;
        private readonly IUnityViewport viewport;
        private readonly object gate = new object();
        private readonly Dictionary<ulong, TaskCompletionSource<WebViewResult>> pending =
            new Dictionary<ulong, TaskCompletionSource<WebViewResult>>();
        private readonly Dictionary<ulong, BridgeCompletion> earlyCompletions =
            new Dictionary<ulong, BridgeCompletion>();
        private int startsInProgress;

        public WebView()
            : this(
                UnityBridgeFactory.Create(),
                new UnityMainThreadScheduler(),
                new UnityViewport())
        {
        }

        internal WebView(
            IWebViewBridge bridge,
            IUnityMainThreadScheduler mainThread,
            IUnityViewport viewport)
        {
            this.bridge = bridge ?? throw new ArgumentNullException(nameof(bridge));
            this.mainThread = mainThread ?? throw new ArgumentNullException(nameof(mainThread));
            this.viewport = viewport ?? throw new ArgumentNullException(nameof(viewport));
            bridge.Completed += OnBridgeCompleted;
        }

        public Task<WebViewResult> InitializeAsync(WebViewOptions options)
        {
            if (options == null)
            {
                return CompletedResult(WebViewErrorCode.InvalidOptions);
            }
            return Begin(() => bridge.Initialize(options), false);
        }

        public Task<WebViewResult> OpenAsync(string url, Rect? rectangle = null)
        {
            if (url == null)
            {
                return CompletedResult(WebViewErrorCode.InvalidUrl);
            }

            NormalizedGeometry geometry = rectangle.HasValue
                ? GeometryConverter.FromUnityRect(rectangle.Value, viewport.Width, viewport.Height)
                : NormalizedGeometry.FullScreen;
            return Begin(() => bridge.Open(url, geometry), false);
        }

        public Task<WebViewResult> CloseAsync()
        {
            return Begin(bridge.Close, false);
        }

        public Task<WebViewResult> DisposeAsync()
        {
            return Begin(bridge.Dispose, true);
        }

        private Task<WebViewResult> Begin(Func<BridgeStartResult> startOperation, bool isDispose)
        {
            lock (gate)
            {
                startsInProgress++;
            }

            BridgeStartResult start;
            try
            {
                start = startOperation();
            }
            catch
            {
                lock (gate)
                {
                    startsInProgress--;
                    if (startsInProgress == 0)
                    {
                        earlyCompletions.Clear();
                    }
                }
                throw;
            }

            if (!start.IsAccepted)
            {
                lock (gate)
                {
                    startsInProgress--;
                    if (startsInProgress == 0)
                    {
                        earlyCompletions.Clear();
                    }
                }
                return Task.FromResult(MapResult(start.WireCode, start.Diagnostic));
            }

            List<TaskCompletionSource<WebViewResult>> retired =
                new List<TaskCompletionSource<WebViewResult>>();
            var completion = new TaskCompletionSource<WebViewResult>();
            BridgeCompletion? early = null;
            lock (gate)
            {
                if (isDispose)
                {
                    retired.AddRange(pending.Values);
                    pending.Clear();
                }
                pending.Add(start.Operation, completion);
                if (earlyCompletions.TryGetValue(start.Operation, out BridgeCompletion value))
                {
                    early = value;
                    earlyCompletions.Remove(start.Operation);
                }
                startsInProgress--;
                if (startsInProgress == 0)
                {
                    earlyCompletions.Clear();
                }
            }

            foreach (TaskCompletionSource<WebViewResult> source in retired)
            {
                PostResult(source, new WebViewResult(WebViewErrorCode.Disposed));
            }
            if (early.HasValue)
            {
                CompleteRegistered(early.Value);
            }
            return completion.Task;
        }

        private void OnBridgeCompleted(BridgeCompletion completion)
        {
            TaskCompletionSource<WebViewResult> source;
            lock (gate)
            {
                if (!pending.TryGetValue(completion.Operation, out source))
                {
                    if (startsInProgress > 0 && !earlyCompletions.ContainsKey(completion.Operation))
                    {
                        earlyCompletions.Add(completion.Operation, completion);
                    }
                    return;
                }
                pending.Remove(completion.Operation);
            }
            PostResult(source, MapResult(completion.WireCode, completion.Diagnostic));
        }

        private void CompleteRegistered(BridgeCompletion completion)
        {
            TaskCompletionSource<WebViewResult> source;
            lock (gate)
            {
                if (!pending.TryGetValue(completion.Operation, out source))
                {
                    return;
                }
                pending.Remove(completion.Operation);
            }
            PostResult(source, MapResult(completion.WireCode, completion.Diagnostic));
        }

        private void PostResult(TaskCompletionSource<WebViewResult> source, WebViewResult result)
        {
            mainThread.Post(() => source.TrySetResult(result));
        }

        private static Task<WebViewResult> CompletedResult(WebViewErrorCode code)
        {
            return Task.FromResult(new WebViewResult(code));
        }

        private static WebViewResult MapResult(uint wireCode, string? diagnostic)
        {
            if (!WebViewErrorCodeMapping.TryFromWire(wireCode, out WebViewErrorCode code))
            {
                return new WebViewResult(
                    WebViewErrorCode.AbiMismatch,
                    DiagnosticDetail.UnknownWireCode(wireCode, diagnostic));
            }
            return new WebViewResult(code, DiagnosticDetail.Normalize(diagnostic));
        }
    }
}
