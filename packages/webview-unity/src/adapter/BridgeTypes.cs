#nullable enable
using System;

namespace Verve.WebView
{
    internal readonly struct NormalizedGeometry
    {
        internal NormalizedGeometry(double x, double y, double width, double height)
        {
            X = x;
            Y = y;
            Width = width;
            Height = height;
        }

        internal double X { get; }
        internal double Y { get; }
        internal double Width { get; }
        internal double Height { get; }

        internal static NormalizedGeometry FullScreen { get; } =
            new NormalizedGeometry(0.0, 0.0, 1.0, 1.0);
    }

    internal readonly struct BridgeStartResult
    {
        private BridgeStartResult(bool isAccepted, ulong operation, uint wireCode, string? diagnostic)
        {
            IsAccepted = isAccepted;
            Operation = operation;
            WireCode = wireCode;
            Diagnostic = diagnostic;
        }

        internal bool IsAccepted { get; }
        internal ulong Operation { get; }
        internal uint WireCode { get; }
        internal string? Diagnostic { get; }

        internal static BridgeStartResult Accepted(ulong operation)
        {
            return new BridgeStartResult(true, operation, 0, null);
        }

        internal static BridgeStartResult Rejected(uint wireCode, string? diagnostic = null)
        {
            return new BridgeStartResult(false, 0, wireCode, diagnostic);
        }
    }

    internal readonly struct BridgeCompletion
    {
        internal BridgeCompletion(ulong operation, uint wireCode, string? diagnostic)
        {
            Operation = operation;
            WireCode = wireCode;
            Diagnostic = diagnostic;
        }

        internal ulong Operation { get; }
        internal uint WireCode { get; }
        internal string? Diagnostic { get; }
    }

    /// <summary>
    /// Engine-side lifecycle seam implemented by Binding Targets.
    /// Opaque Core handles and the physical event transport never cross it.
    /// </summary>
    internal interface IWebViewBridge
    {
        event Action<BridgeCompletion>? Completed;

        BridgeStartResult Initialize(WebViewOptions options);
        BridgeStartResult Open(string url, NormalizedGeometry geometry);
        BridgeStartResult Close();
        BridgeStartResult Dispose();
    }

    /// <summary>
    /// Resolves the currently valid engine host capability for each UI operation.
    /// Returned capabilities are borrowed and must never be retained or released.
    /// </summary>
    internal interface IUnityHostLocator
    {
        object? LocateHost();
    }

    internal interface IUnityMainThreadScheduler
    {
        void Post(Action action);
    }

    internal interface IUnityViewport
    {
        int Width { get; }
        int Height { get; }
    }
}
