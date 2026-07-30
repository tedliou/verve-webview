using System;
using System.IO;
using System.Linq;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.PackageManager;
using UnityEngine;

namespace Verve.WebView.Editor
{
    internal sealed class WebBuildPostprocessor : IPostprocessBuildWithReport
    {
        private const string PackageId = "com.tedliou.verve-webview";
        private const string Marker = "<!-- VERVE_WEBVIEW_CORE -->";

        public int callbackOrder => 1000;

        public void OnPostprocessBuild(BuildReport report)
        {
            if (report.summary.platform != UnityEditor.BuildTarget.WebGL)
            {
                return;
            }

            PackageInfo package = PackageInfo.GetAllRegisteredPackages()
                .Single(info => info.name == PackageId);
            string source = Path.Combine(package.resolvedPath, "Runtime", "Web", "Core");
            string output = Directory.Exists(report.summary.outputPath)
                ? report.summary.outputPath
                : Path.GetDirectoryName(report.summary.outputPath);
            if (output == null)
            {
                throw new BuildFailedException("Cannot resolve the WebGL output directory.");
            }

            string destination = Path.Combine(output, "VerveWebViewCore");
            Directory.CreateDirectory(destination);
            foreach (string file in new[]
            {
                "api-contract.js",
                "verve_webview_core.js",
                "verve_webview_core_bg.wasm",
                "verve_webview_core_facade.js",
                "verve_webview_web_backend.js",
            })
            {
                File.Copy(Path.Combine(source, file), Path.Combine(destination, file), true);
            }

            string index = Path.Combine(output, "index.html");
            string html = File.ReadAllText(index);
            if (!html.Contains(Marker))
            {
                string scripts = Marker + "\n"
                    + "<script src=\"VerveWebViewCore/api-contract.js\"></script>\n"
                    + "<script src=\"VerveWebViewCore/verve_webview_core.js\"></script>\n"
                    + "<script src=\"VerveWebViewCore/verve_webview_core_facade.js\"></script>\n"
                    + "<script src=\"VerveWebViewCore/verve_webview_web_backend.js\"></script>\n";
                html = html.Replace("</head>", scripts + "</head>");
                File.WriteAllText(index, html);
            }
            Debug.Log("Verve WebView browser Core staged at " + destination);
        }
    }
}
