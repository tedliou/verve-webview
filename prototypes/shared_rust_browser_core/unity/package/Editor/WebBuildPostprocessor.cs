// PROTOTYPE ONLY: package-owned export placement, with no consumer template.
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.PackageManager;
using UnityEngine;

namespace Verve.WebView.Prototype.Editor
{
    internal sealed class WebBuildPostprocessor : IPostprocessBuildWithReport
    {
        public int callbackOrder => 1000;

        public void OnPostprocessBuild(BuildReport report)
        {
            if (report.summary.platform != BuildTarget.WebGL) return;

            var package = UnityEditor.PackageManager.PackageInfo.GetAllRegisteredPackages()
                .Single(info => info.name == "com.tedliou.verve.webview.prototype");
            var source = Path.Combine(package.resolvedPath, "Runtime", "Web", "Core");
            var output = Directory.Exists(report.summary.outputPath)
                ? report.summary.outputPath
                : Path.GetDirectoryName(report.summary.outputPath);
            if (output == null) throw new BuildFailedException("Cannot resolve WebGL output directory.");

            var destination = Path.Combine(output, "VerveWebViewCore");
            Directory.CreateDirectory(destination);
            foreach (var file in new[] {
                "verve_webview_core.js",
                "verve_webview_core_bg.wasm",
                "verve_webview_core_facade.js"
            }) {
                File.Copy(Path.Combine(source, file), Path.Combine(destination, file), true);
            }

            var index = Path.Combine(output, "index.html");
            var html = File.ReadAllText(index);
            const string marker = "<!-- VERVE_WEBVIEW_CORE_PROTOTYPE -->";
            if (!html.Contains(marker)) {
                var scripts = marker + "\n"
                    + "<script src=\"VerveWebViewCore/verve_webview_core.js\"></script>\n"
                    + "<script src=\"VerveWebViewCore/verve_webview_core_facade.js\"></script>\n";
                html = html.Replace("</head>", scripts + "</head>");
                File.WriteAllText(index, html);
            }
            Debug.Log("VERVE_PROTOTYPE Unity browser Core staged at " + destination);
        }
    }
}
