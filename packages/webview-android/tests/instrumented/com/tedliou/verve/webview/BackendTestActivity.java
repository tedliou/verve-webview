package com.tedliou.verve.webview;

import android.app.Activity;
import android.os.Bundle;
import android.widget.FrameLayout;

public final class BackendTestActivity extends Activity {
  public FrameLayout host;

  @Override
  protected void onCreate(Bundle state) {
    super.onCreate(state);
    host = new FrameLayout(this);
    host.setTag("verve-webview-test-host");
    setContentView(host);
  }
}
