#nullable enable
using System;
using System.Threading;
using UnityEngine;

namespace Verve.WebView
{
    internal sealed class UnityMainThreadScheduler : IUnityMainThreadScheduler
    {
        private readonly SynchronizationContext context;

        internal UnityMainThreadScheduler()
        {
            context = SynchronizationContext.Current
                ?? throw new InvalidOperationException(
                    "WebView must be created on the Unity main thread.");
        }

        public void Post(Action action)
        {
            context.Post(_ => action(), null);
        }
    }

    internal sealed class UnityViewport : IUnityViewport
    {
        public int Width => Screen.width;
        public int Height => Screen.height;
    }

    internal static class UnityBridgeFactory
    {
        internal static IWebViewBridge Create()
        {
#if UNITY_EDITOR
            return new EditorFakeWebViewBridge(SynchronizationContext.Current);
#elif UNITY_ANDROID || UNITY_IOS || UNITY_STANDALONE_WIN || UNITY_WEBGL
            return UnityBindingRegistry.CreateOrMissing();
#else
            return new UnsupportedEnvironmentBridge();
#endif
        }
    }

    /// <summary>
    /// Composition seam used by the platform-selected Binding Target.
    /// The Adapter retains the locator capability, never a located host.
    /// </summary>
    internal static class UnityBindingRegistry
    {
        private static readonly object Gate = new object();
        private static Func<IUnityHostLocator, IWebViewBridge>? factory;
        private static IUnityHostLocator? hostLocator;

        internal static void Install(
            IUnityHostLocator locator,
            Func<IUnityHostLocator, IWebViewBridge> bridgeFactory)
        {
            if (locator == null)
            {
                throw new ArgumentNullException(nameof(locator));
            }
            if (bridgeFactory == null)
            {
                throw new ArgumentNullException(nameof(bridgeFactory));
            }

            lock (Gate)
            {
                if (factory != null)
                {
                    throw new InvalidOperationException(
                        "A Unity Binding Target is already installed.");
                }
                hostLocator = locator;
                factory = bridgeFactory;
            }
        }

        internal static IWebViewBridge CreateOrMissing()
        {
            lock (Gate)
            {
                if (factory == null || hostLocator == null)
                {
                    return new MissingBindingBridge();
                }
                return factory(hostLocator)
                    ?? throw new InvalidOperationException(
                        "The Unity Binding Target returned no bridge.");
            }
        }
    }

    internal sealed class UnsupportedEnvironmentBridge : IWebViewBridge
    {
        private const string Detail = "Verve WebView is unavailable in this Unity environment.";
        private bool disposed;

        public event Action<BridgeCompletion>? Completed
        {
            add { }
            remove { }
        }

        public BridgeStartResult Initialize(WebViewOptions options) =>
            disposed ? Disposed() : Unsupported();
        public BridgeStartResult Open(string url, NormalizedGeometry geometry) =>
            disposed ? Disposed() : NotInitialized();
        public BridgeStartResult Close() =>
            disposed ? Disposed() : NotInitialized();
        public BridgeStartResult Dispose()
        {
            if (disposed)
            {
                return Disposed();
            }
            disposed = true;
            return BridgeStartResult.Rejected((uint)WebViewErrorCode.Ok);
        }

        private static BridgeStartResult Unsupported()
        {
            return BridgeStartResult.Rejected((uint)WebViewErrorCode.UnsupportedEnvironment, Detail);
        }

        private static BridgeStartResult NotInitialized() =>
            BridgeStartResult.Rejected((uint)WebViewErrorCode.NotInitialized);

        private static BridgeStartResult Disposed() =>
            BridgeStartResult.Rejected((uint)WebViewErrorCode.Disposed);
    }

    internal sealed class MissingBindingBridge : IWebViewBridge
    {
        private const string Detail = "The required Unity Binding Target is not installed.";
        private bool disposed;

        public event Action<BridgeCompletion>? Completed
        {
            add { }
            remove { }
        }

        public BridgeStartResult Initialize(WebViewOptions options) =>
            disposed ? Disposed() : Missing();
        public BridgeStartResult Open(string url, NormalizedGeometry geometry) =>
            disposed ? Disposed() : NotInitialized();
        public BridgeStartResult Close() =>
            disposed ? Disposed() : NotInitialized();
        public BridgeStartResult Dispose()
        {
            if (disposed)
            {
                return Disposed();
            }
            disposed = true;
            return BridgeStartResult.Rejected((uint)WebViewErrorCode.Ok);
        }

        private static BridgeStartResult Missing()
        {
            return BridgeStartResult.Rejected((uint)WebViewErrorCode.DistributionInvalid, Detail);
        }

        private static BridgeStartResult NotInitialized() =>
            BridgeStartResult.Rejected((uint)WebViewErrorCode.NotInitialized);

        private static BridgeStartResult Disposed() =>
            BridgeStartResult.Rejected((uint)WebViewErrorCode.Disposed);
    }
}
