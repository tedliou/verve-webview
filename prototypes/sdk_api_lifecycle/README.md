# PROTOTYPE — SDK API lifecycle

This throwaway prototype asks whether the proposed Unity and Godot interfaces make the
same single-surface lifecycle feel predictable when commands overlap, fail, repeat, or
complete late. It is a decision aid, not production SDK code.

Run it with:

```sh
python3 prototypes/sdk_api_lifecycle/tui.py
```

Drive the SDK Instance with the displayed keys. In particular, try disposing while an
operation is pending, completing the retired operation late, opening a second URL while
the WebView Surface is visible, and repeating every command.
