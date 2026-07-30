#nullable enable
using System.Threading.Tasks;
using UnityEngine;
using Verve.WebView;

public sealed class VerveWebViewExample : MonoBehaviour
{
    private WebView? webView;
    private string status = "Ready";
    private Rect rectangle = new Rect(40, 80, 640, 360);

    private async void OnGUI()
    {
        GUI.Label(new Rect(20, 20, 900, 30), "Status / visible error: " + status);
        if (GUI.Button(new Rect(20, 55, 120, 35), "Initialize"))
            await Initialize();
        if (GUI.Button(new Rect(150, 55, 120, 35), "Open"))
            await Open("https://example.com/");
        if (GUI.Button(new Rect(280, 55, 120, 35), "Navigate"))
            await Navigate();
        if (GUI.Button(new Rect(410, 55, 120, 35), "Rectangle"))
            await UpdateRectangle();
        if (GUI.Button(new Rect(540, 55, 120, 35), "Close"))
            await Close();
        if (GUI.Button(new Rect(670, 55, 120, 35), "Reopen"))
            await Reopen();
        if (GUI.Button(new Rect(800, 55, 120, 35), "Dispose"))
            await Dispose();
    }

    private async Task Initialize()
    {
        webView ??= new WebView();
        Report("initialize", await webView.InitializeAsync(WebViewOptions.Default));
    }

    private async Task Open(string url)
    {
        if (webView == null) { status = "error: initialize first"; return; }
        Report("open", await webView.OpenAsync(url, rectangle));
    }

    private Task Navigate() => Open("https://www.example.com/");

    private async Task UpdateRectangle()
    {
        rectangle = new Rect(80, 120, 520, 300);
        await Open("https://www.example.com/?rectangle=updated");
    }

    private async Task Close()
    {
        if (webView == null) { status = "error: initialize first"; return; }
        Report("close", await webView.CloseAsync());
    }

    private async Task Reopen()
    {
        await Close();
        await Open("https://example.com/?reopen=true");
    }

    private async Task Dispose()
    {
        if (webView == null) { status = "error: initialize first"; return; }
        Report("dispose", await webView.DisposeAsync());
    }

    private void Report(string operation, WebViewResult result)
    {
        status = result.IsSuccess
            ? operation + ": ok"
            : $"error: {operation}: {result.Code}: {result.DiagnosticDetail}";
        Debug.Log(status);
    }
}
