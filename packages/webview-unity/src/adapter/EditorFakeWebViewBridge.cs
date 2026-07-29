#nullable enable
using System;
using System.Threading;

namespace Verve.WebView
{
    internal sealed class EditorFakeWebViewBridge : IWebViewBridge
    {
        private enum Phase
        {
            Uninitialized,
            InitializedClosed,
            SurfaceOpen,
            Disposing,
            Disposed,
        }

        private readonly SynchronizationContext context;
        private Phase phase;
        private bool operationInProgress;
        private ulong nextOperation = 1;
        private uint generation;

        internal EditorFakeWebViewBridge(SynchronizationContext? context)
        {
            this.context = context ?? new SynchronizationContext();
        }

        public event Action<BridgeCompletion>? Completed;

        public BridgeStartResult Initialize(WebViewOptions options)
        {
            if (phase == Phase.Disposing || phase == Phase.Disposed)
            {
                return Reject(WebViewErrorCode.Disposed);
            }
            if (operationInProgress)
            {
                return Reject(WebViewErrorCode.OperationInProgress);
            }
            if (phase != Phase.Uninitialized)
            {
                return Reject(WebViewErrorCode.AlreadyInitialized);
            }
            return Accept(Phase.InitializedClosed);
        }

        public BridgeStartResult Open(string url, NormalizedGeometry geometry)
        {
            if (phase == Phase.Disposing || phase == Phase.Disposed)
            {
                return Reject(WebViewErrorCode.Disposed);
            }
            if (operationInProgress)
            {
                return Reject(WebViewErrorCode.OperationInProgress);
            }
            if (phase == Phase.Uninitialized)
            {
                return Reject(WebViewErrorCode.NotInitialized);
            }
            if (!Uri.TryCreate(url, UriKind.Absolute, out Uri parsed) ||
                (parsed.Scheme != Uri.UriSchemeHttp && parsed.Scheme != Uri.UriSchemeHttps) ||
                !string.IsNullOrEmpty(parsed.UserInfo))
            {
                return Reject(WebViewErrorCode.InvalidUrl);
            }
            if (!IsValid(geometry))
            {
                return Reject(WebViewErrorCode.InvalidGeometry);
            }
            return Accept(Phase.SurfaceOpen);
        }

        public BridgeStartResult Close()
        {
            if (phase == Phase.Disposing || phase == Phase.Disposed)
            {
                return Reject(WebViewErrorCode.Disposed);
            }
            if (operationInProgress)
            {
                return Reject(WebViewErrorCode.OperationInProgress);
            }
            if (phase == Phase.Uninitialized)
            {
                return Reject(WebViewErrorCode.NotInitialized);
            }
            if (phase != Phase.SurfaceOpen)
            {
                return Reject(WebViewErrorCode.SurfaceNotOpen);
            }
            return Accept(Phase.InitializedClosed);
        }

        public BridgeStartResult Dispose()
        {
            if (phase == Phase.Disposing || phase == Phase.Disposed)
            {
                return Reject(WebViewErrorCode.Disposed);
            }

            operationInProgress = false;
            phase = Phase.Disposing;
            generation++;
            return Accept(Phase.Disposed);
        }

        private BridgeStartResult Accept(Phase completedPhase)
        {
            ulong operation = nextOperation++;
            uint acceptedGeneration = generation;
            operationInProgress = true;
            context.Post(
                _ =>
                {
                    if (acceptedGeneration != generation)
                    {
                        return;
                    }
                    operationInProgress = false;
                    phase = completedPhase;
                    Completed?.Invoke(new BridgeCompletion(
                        operation,
                        (uint)WebViewErrorCode.Ok,
                        null));
                },
                null);
            return BridgeStartResult.Accepted(operation);
        }

        private static BridgeStartResult Reject(WebViewErrorCode code)
        {
            return BridgeStartResult.Rejected((uint)code);
        }

        private static bool IsValid(NormalizedGeometry geometry)
        {
            return IsFinite(geometry.X) &&
                   IsFinite(geometry.Y) &&
                   IsFinite(geometry.Width) &&
                   IsFinite(geometry.Height) &&
                   geometry.X >= 0.0 &&
                   geometry.Y >= 0.0 &&
                   geometry.Width > 0.0 &&
                   geometry.Height > 0.0 &&
                   geometry.X + geometry.Width <= 1.0 &&
                   geometry.Y + geometry.Height <= 1.0;
        }

        private static bool IsFinite(double value)
        {
            return !double.IsNaN(value) && !double.IsInfinity(value);
        }
    }
}
