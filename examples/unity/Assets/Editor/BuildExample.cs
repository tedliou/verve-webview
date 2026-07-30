using System;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class BuildExample
{
    public static void Build()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects);
        new GameObject("VerveWebViewExample").AddComponent<VerveWebViewExample>();
        const string scenePath = "Assets/VerveWebViewExample.unity";
        EditorSceneManager.SaveScene(scene, scenePath);
        string target = Environment.GetEnvironmentVariable("VERVE_BUILD_TARGET") ?? "WebGL";
        BuildTarget buildTarget = target == "StandaloneWindows64"
            ? BuildTarget.StandaloneWindows64 : BuildTarget.WebGL;
        string output = target == "StandaloneWindows64"
            ? "Build/Windows/VerveWebViewExample.exe" : "Build/WebGL";
        var report = BuildPipeline.BuildPlayer(
            new[] { scenePath }, output, buildTarget, BuildOptions.None);
        if (report.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded)
            throw new InvalidOperationException(report.summary.ToString());
    }
}
