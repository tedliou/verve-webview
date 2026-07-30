#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using UnityEngine;

namespace Verve.WebView.Tests
{
    public sealed class WebViewAdapterTests
    {
        [Test]
        public void GeneratedPublicApiUsesPascalCaseStableWireIds()
        {
            var expected = new Dictionary<string, uint>
            {
                ["Ok"] = 0,
                ["InvalidOptions"] = 100,
                ["InvalidUrl"] = 101,
                ["InvalidGeometry"] = 102,
                ["NotInitialized"] = 200,
                ["AlreadyInitialized"] = 201,
                ["OperationInProgress"] = 202,
                ["Disposed"] = 203,
                ["SurfaceNotOpen"] = 204,
                ["SurfaceInUse"] = 205,
                ["HostUnavailable"] = 300,
                ["HostLost"] = 301,
                ["BackendFailure"] = 302,
                ["CleanupFailed"] = 303,
                ["CoreLoadFailed"] = 400,
                ["AbiMismatch"] = 401,
                ["RuntimeUnavailable"] = 402,
                ["UnsupportedEnvironment"] = 403,
                ["DistributionInvalid"] = 404,
                ["InternalFailure"] = 500,
            };
            Array values = Enum.GetValues(typeof(WebViewErrorCode));
            Assert.That(values.Length, Is.EqualTo(expected.Count));
            foreach (WebViewErrorCode value in values)
            {
                Assert.That(expected[value.ToString()], Is.EqualTo((uint)value));
                Assert.That(
                    WebViewErrorCodeMapping.TryFromWire((uint)value, out WebViewErrorCode mapped),
                    Is.True);
                Assert.That(mapped, Is.EqualTo(value));
            }

            Assert.That(typeof(WebViewResult).IsValueType, Is.True);
            Assert.That(typeof(WebViewResult).GetFields(BindingFlags.Instance | BindingFlags.Public), Is.Empty);

            MethodInfo[] methods = typeof(WebView).GetMethods(BindingFlags.Instance | BindingFlags.Public);
            Assert.That(methods.Single(method => method.Name == "InitializeAsync").ReturnType,
                Is.EqualTo(typeof(Task<WebViewResult>)));
            Assert.That(methods.Single(method => method.Name == "OpenAsync").ReturnType,
                Is.EqualTo(typeof(Task<WebViewResult>)));
            Assert.That(methods.Single(method => method.Name == "CloseAsync").ReturnType,
                Is.EqualTo(typeof(Task<WebViewResult>)));
            Assert.That(methods.Single(method => method.Name == "DisposeAsync").ReturnType,
                Is.EqualTo(typeof(Task<WebViewResult>)));
        }

        [Test]
        public void UnityRectConvertsFromBottomLeftPixelsToNormalizedTopLeftGeometry()
        {
            NormalizedGeometry geometry = GeometryConverter.FromUnityRect(
                new Rect(20f, 10f, 40f, 30f),
                200,
                100);

            Assert.That(geometry.X, Is.EqualTo(0.1).Within(0.000001));
            Assert.That(geometry.Y, Is.EqualTo(0.6).Within(0.000001));
            Assert.That(geometry.Width, Is.EqualTo(0.2).Within(0.000001));
            Assert.That(geometry.Height, Is.EqualTo(0.3).Within(0.000001));
        }

        [Test]
        public void ExpectedFailuresCompleteNormallyAndUnknownWireIdsMapToAbiMismatch()
        {
            var bridge = new ControllableBridge();
            var scheduler = new ImmediateMainThreadScheduler();
            var webView = new WebView(bridge, scheduler, new FixedViewport(200, 100));

            Task<WebViewResult> operation = webView.InitializeAsync(WebViewOptions.Default);
            bridge.Complete(777, "received unknown wire code");
            WebViewResult result = operation.GetAwaiter().GetResult();

            Assert.That(result.Code, Is.EqualTo(WebViewErrorCode.AbiMismatch));
            Assert.That(result.DiagnosticDetail, Does.Contain("777"));
            Assert.That(operation.IsFaulted, Is.False);
        }

        [Test]
        public void DisposePreemptsPendingOperationAndLateCompletionIsIgnored()
        {
            var bridge = new ControllableBridge();
            var scheduler = new ImmediateMainThreadScheduler();
            var webView = new WebView(bridge, scheduler, new FixedViewport(200, 100));

            Task<WebViewResult> initialize = webView.InitializeAsync(WebViewOptions.Default);
            Task<WebViewResult> dispose = webView.DisposeAsync();

            WebViewResult retired = initialize.GetAwaiter().GetResult();
            Assert.That(retired.Code, Is.EqualTo(WebViewErrorCode.Disposed));

            bridge.CompleteOperation(1, (uint)WebViewErrorCode.Ok, null);
            Assert.That(dispose.IsCompleted, Is.False);

            bridge.CompleteOperation(2, (uint)WebViewErrorCode.Ok, null);
            Assert.That(dispose.GetAwaiter().GetResult().Code, Is.EqualTo(WebViewErrorCode.Ok));
        }

        [Test]
        public void DiagnosticDetailIsSanitizedAndUtf8Bounded()
        {
            var bridge = new ControllableBridge();
            var webView = new WebView(
                bridge,
                new ImmediateMainThreadScheduler(),
                new FixedViewport(200, 100));
            string unsafeDetail = "stage https://example.com/path?secret=yes " + new string('界', 600);

            Task<WebViewResult> operation = webView.InitializeAsync(WebViewOptions.Default);
            bridge.Complete((uint)WebViewErrorCode.BackendFailure, unsafeDetail);
            WebViewResult result = operation.GetAwaiter().GetResult();

            Assert.That(result.DiagnosticDetail, Does.Not.Contain("example.com"));
            Assert.That(Encoding.UTF8.GetByteCount(result.DiagnosticDetail!), Is.LessThanOrEqualTo(1024));
        }

        [Test]
        public void CompletionFromWorkerThreadResolvesOnCapturedUnityMainThread()
        {
            int mainThread = Thread.CurrentThread.ManagedThreadId;
            var scheduler = new PumpMainThreadScheduler(mainThread);
            var bridge = new ControllableBridge();
            var webView = new WebView(bridge, scheduler, new FixedViewport(200, 100));

            Task<WebViewResult> operation = webView.InitializeAsync(WebViewOptions.Default);
            Task.Run(() => bridge.Complete((uint)WebViewErrorCode.Ok, null))
                .GetAwaiter()
                .GetResult();
            Assert.That(operation.IsCompleted, Is.False);

            scheduler.Pump();
            WebViewResult result = operation.GetAwaiter().GetResult();
            Assert.That(result.IsSuccess, Is.True);
            Assert.That(scheduler.LastExecutionThread, Is.EqualTo(mainThread));
        }

        [Test]
        public void WorkerCompletionBeforeBridgeReturnsStillResolvesExactlyOnce()
        {
            var bridge = new EagerWorkerBridge();
            var webView = new WebView(
                bridge,
                new ImmediateMainThreadScheduler(),
                new FixedViewport(200, 100));

            Task<WebViewResult> operation = webView.InitializeAsync(WebViewOptions.Default);

            Assert.That(operation.Wait(1000), Is.True);
            Assert.That(operation.GetAwaiter().GetResult().IsSuccess, Is.True);
        }

        [Test]
        public void UnsupportedEnvironmentIsDeterministic()
        {
            var webView = new WebView(
                new UnsupportedEnvironmentBridge(),
                new ImmediateMainThreadScheduler(),
                new FixedViewport(200, 100));

            WebViewResult first = webView.InitializeAsync(WebViewOptions.Default)
                .GetAwaiter()
                .GetResult();
            WebViewResult second = webView.InitializeAsync(WebViewOptions.Default)
                .GetAwaiter()
                .GetResult();

            Assert.That(first.Code, Is.EqualTo(WebViewErrorCode.UnsupportedEnvironment));
            Assert.That(second.Code, Is.EqualTo(WebViewErrorCode.UnsupportedEnvironment));
            Assert.That(first.DiagnosticDetail, Is.EqualTo(second.DiagnosticDetail));
        }

        [Test]
        public void EditorFakeImplementsReusableSurfaceLifecycleAndTerminalDisposal()
        {
            var context = new PumpSynchronizationContext();
            var bridge = new EditorFakeWebViewBridge(context);
            var webView = new WebView(
                bridge,
                new ImmediateMainThreadScheduler(),
                new FixedViewport(200, 100));

            Task<WebViewResult> initialize = webView.InitializeAsync(WebViewOptions.Default);
            Assert.That(initialize.IsCompleted, Is.False);
            Assert.That(
                webView.InitializeAsync(WebViewOptions.Default).GetAwaiter().GetResult().Code,
                Is.EqualTo(WebViewErrorCode.OperationInProgress));
            context.Pump();
            Assert.That(initialize.GetAwaiter().GetResult().IsSuccess, Is.True);
            Assert.That(
                webView.InitializeAsync(WebViewOptions.Default).GetAwaiter().GetResult().Code,
                Is.EqualTo(WebViewErrorCode.AlreadyInitialized));

            Task<WebViewResult> firstOpen = webView.OpenAsync("https://example.test");
            context.Pump();
            Assert.That(firstOpen.GetAwaiter().GetResult().IsSuccess, Is.True);

            Task<WebViewResult> navigation = webView.OpenAsync("https://example.test/next");
            context.Pump();
            Assert.That(navigation.GetAwaiter().GetResult().IsSuccess, Is.True);

            Task<WebViewResult> close = webView.CloseAsync();
            context.Pump();
            Assert.That(close.GetAwaiter().GetResult().IsSuccess, Is.True);
            Assert.That(
                webView.CloseAsync().GetAwaiter().GetResult().Code,
                Is.EqualTo(WebViewErrorCode.SurfaceNotOpen));

            Task<WebViewResult> dispose = webView.DisposeAsync();
            context.Pump();
            Assert.That(dispose.GetAwaiter().GetResult().IsSuccess, Is.True);
            Assert.That(
                webView.OpenAsync("https://example.test").GetAwaiter().GetResult().Code,
                Is.EqualTo(WebViewErrorCode.Disposed));
            Assert.That(
                webView.DisposeAsync().GetAwaiter().GetResult().Code,
                Is.EqualTo(WebViewErrorCode.Disposed));
        }
    }
}
