#nullable enable

namespace Verve.WebView
{
    /// <summary>
    /// Initialization options for one SDK Instance.
    /// </summary>
    /// <remarks>
    /// Version 1 currently has no caller-selectable fields. Keeping the value
    /// explicit preserves the generated four-operation API without exposing
    /// Binding Target or Platform Backend configuration.
    /// </remarks>
    public sealed class WebViewOptions
    {
        public static WebViewOptions Default { get; } = new WebViewOptions();

        public WebViewOptions()
        {
        }
    }
}
