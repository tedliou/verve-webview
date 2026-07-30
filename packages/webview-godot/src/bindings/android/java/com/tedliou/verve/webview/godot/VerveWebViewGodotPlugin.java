package com.tedliou.verve.webview.godot;

import org.godotengine.godot.Godot;
import org.godotengine.godot.plugin.GodotPlugin;

/** Godot v2 registration wrapper; reusable WebView behavior remains in the Backend AAR. */
public final class VerveWebViewGodotPlugin extends GodotPlugin {
  public VerveWebViewGodotPlugin(Godot godot) {
    super(godot);
  }

  @Override
  public String getPluginName() {
    return "VerveWebView";
  }
}
