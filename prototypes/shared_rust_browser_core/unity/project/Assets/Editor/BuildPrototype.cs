// PROTOTYPE ONLY: deterministic release WebGL export entry point.
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class BuildPrototype
{
    public static void Build()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        new GameObject("PrototypeRunner").AddComponent<PrototypeRunner>();
        Directory.CreateDirectory("Assets/Scenes");
        const string scenePath = "Assets/Scenes/Prototype.unity";
        EditorSceneManager.SaveScene(scene, scenePath);

        PlayerSettings.SetManagedStrippingLevel(BuildTargetGroup.WebGL, ManagedStrippingLevel.High);
        PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Disabled;
        PlayerSettings.productName = "Verve WebView Core Prototype";

        var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions {
            scenes = new[] { scenePath },
            locationPathName = Path.GetFullPath("Build/WebGL"),
            target = BuildTarget.WebGL,
            options = BuildOptions.None
        });
        if (report.summary.result != BuildResult.Succeeded) {
            throw new BuildFailedException("Unity WebGL prototype export failed: " + report.summary.result);
        }
    }
}
