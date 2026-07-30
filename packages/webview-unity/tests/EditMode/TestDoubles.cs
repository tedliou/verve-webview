#nullable enable
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Verve.WebView.Tests
{
    internal sealed class FixedViewport : IUnityViewport
    {
        public FixedViewport(int width, int height)
        {
            Width = width;
            Height = height;
        }

        public int Width { get; }
        public int Height { get; }
    }

    internal sealed class ImmediateMainThreadScheduler : IUnityMainThreadScheduler
    {
        public void Post(Action action)
        {
            action();
        }
    }

    internal sealed class PumpMainThreadScheduler : IUnityMainThreadScheduler
    {
        private readonly Queue<Action> queue = new Queue<Action>();

        public PumpMainThreadScheduler(int mainThread)
        {
            MainThread = mainThread;
        }

        public int MainThread { get; }
        public int LastExecutionThread { get; private set; }

        public void Post(Action action)
        {
            lock (queue)
            {
                queue.Enqueue(action);
            }
        }

        public void Pump()
        {
            while (true)
            {
                Action action;
                lock (queue)
                {
                    if (queue.Count == 0)
                    {
                        return;
                    }
                    action = queue.Dequeue();
                }

                LastExecutionThread = Thread.CurrentThread.ManagedThreadId;
                action();
            }
        }
    }

    internal sealed class PumpSynchronizationContext : SynchronizationContext
    {
        private readonly Queue<(SendOrPostCallback Callback, object? State)> queue =
            new Queue<(SendOrPostCallback Callback, object? State)>();

        public override void Post(SendOrPostCallback callback, object? state)
        {
            queue.Enqueue((callback, state));
        }

        public void Pump()
        {
            while (queue.Count > 0)
            {
                (SendOrPostCallback callback, object? state) = queue.Dequeue();
                callback(state);
            }
        }
    }

    internal sealed class ControllableBridge : IWebViewBridge
    {
        private ulong nextOperation = 1;

        public event Action<BridgeCompletion>? Completed;

        public BridgeStartResult Initialize(WebViewOptions options)
        {
            return Accept();
        }

        public BridgeStartResult Open(string url, NormalizedGeometry geometry)
        {
            return Accept();
        }

        public BridgeStartResult Close()
        {
            return Accept();
        }

        public BridgeStartResult Dispose()
        {
            return Accept();
        }

        public void Complete(uint wireCode, string? diagnostic)
        {
            CompleteOperation(nextOperation - 1, wireCode, diagnostic);
        }

        public void CompleteOperation(ulong operation, uint wireCode, string? diagnostic)
        {
            Completed?.Invoke(new BridgeCompletion(operation, wireCode, diagnostic));
        }

        private BridgeStartResult Accept()
        {
            return BridgeStartResult.Accepted(nextOperation++);
        }
    }

    internal sealed class EagerWorkerBridge : IWebViewBridge
    {
        public event Action<BridgeCompletion>? Completed;

        public BridgeStartResult Initialize(WebViewOptions options)
        {
            Task.Run(() => Completed?.Invoke(new BridgeCompletion(
                    1,
                    (uint)WebViewErrorCode.Ok,
                    null)))
                .GetAwaiter()
                .GetResult();
            return BridgeStartResult.Accepted(1);
        }

        public BridgeStartResult Open(string url, NormalizedGeometry geometry) =>
            BridgeStartResult.Rejected((uint)WebViewErrorCode.NotInitialized);

        public BridgeStartResult Close() =>
            BridgeStartResult.Rejected((uint)WebViewErrorCode.NotInitialized);

        public BridgeStartResult Dispose() =>
            BridgeStartResult.Rejected((uint)WebViewErrorCode.Ok);
    }
}
