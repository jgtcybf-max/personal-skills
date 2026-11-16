---
name: douyin-delete-all-works
description: Delete every work from the Works tab in an already-open, logged-in Douyin Creator Center Google Chrome window on Windows. Use when the user explicitly asks to remove all Douyin Creator Center works, bulk-delete published works, or continue a previously confirmed delete-all run while preserving the current Chrome session. Do not use for drafts, collections, account settings, or deleting only selected works.
---

# Douyin Delete All Works

Delete works sequentially from the current Douyin Creator Center Chrome window by using the bundled Windows UI Automation script.

## Safety Gate

1. Confirm the browser is already open, logged in, and showing `内容管理 > 作品 > 全部`.
2. Read the displayed work count.
3. Require an explicit confirmation containing the scope and count, such as `确认删除全部3995部作品`.
4. Do not run the script without that confirmation. Deletion is irreversible.
5. Do not close, restart, or launch Chrome; do not log out or modify drafts, collections, or account settings.

## Run

Ensure no existing `delete_all_douyin.ps1` process is active, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\TTT\.codex\skills\douyin-delete-all-works\scripts\delete_all_douyin.ps1" -Confirmed
```

The script locates each `删除作品` control, invokes it, invokes `确定` in the confirmation dialog, and immediately continues after the dialog disappears and the work list changes. It does not use fixed mouse coordinates, move the browser, or impose a fixed post-refresh delay.

## Monitor

- Keep the Chrome window open and ask the user not to interact with it during deletion.
- Treat a changed first-card fingerprint, changed accessibility runtime ID, or reduced count with a ready delete control as a successful refresh.
- If the list is unchanged for 30 seconds, invoke Chrome's `重新加载` control and wait for a newly created work list. Retry recovery up to three times, then stop.
- Stop on login loss, CAPTCHA, missing confirmation dialog, missing controls after recovery, or any unexpected page.
- Never start a second copy while one is running.

## Verify

After the script completes, independently confirm all of the following:

- The Works tab reports `作品 (0)` or displays `暂无作品`.
- No `删除作品` control remains.
- Chrome stayed open and logged in.

Do not report completion based only on process exit.
