# no_low_battery_alert

**Low Battery Off** is a small [TrollStore](https://github.com/opa334/TrollStore) app that stops iOS from showing the **20% / 10% low-battery popup**, so it no longer covers your game or video. No jailbreak is needed.

The popup is controlled by a hidden SpringBoard preference. The app flips that preference on and off with one switch. Turn the switch off and iOS behaves normally again.

> **Tested on:** iPhone 11 (iPhone12,1), iOS 16.6.1, TrollStore. See [Compatibility](#compatibility) for what has and has not been verified.

---

## Contents

- [Features](#features)
- [Compatibility](#compatibility)
- [Install](#install)
- [Usage](#usage)
- [How it works](#how-it-works)
- [Limitations and disclaimer](#limitations-and-disclaimer)
- [Build from source](#build-from-source)
- [Project layout](#project-layout)
- [Research notes](#research-notes)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Features

- One switch: hide or restore the low-battery popup.
- Reversible. Turning the switch off deletes the preference, so iOS returns to its default.
- Shows the value currently stored, so you can see what state the device is in.
- Optional respring button (only needed if the change does not apply by itself).
- Tiny: plain Objective-C and UIKit, about 200 lines, one arm64 binary of about 20 KB.

## Compatibility

| iOS version | Status |
|---|---|
| 16.6.1 (iPhone 11) | **Confirmed working on a real device** |
| 14.0, 14.8, 15.0, 15.6.1, 16.0 | Same code path found by static analysis of the system firmware. Not run on a device. |
| 17.0, 17.7 | Same code path found by static analysis. Not run on a device. |
| 18.x, 26.x | Not checked yet (see [Research notes](#research-notes)). |

Notes:

- The app itself needs [TrollStore](https://github.com/opa334/TrollStore) to install. Check TrollStore's own page for the iOS versions and devices it supports.
- "Same code path" means the firmware for that version contains the same check before it builds the low-battery alert. It is evidence, not a guarantee. Only 16.6.1 has been tried on hardware.
- Static analysis was done on iPhone 11 firmware images. Other devices were not examined.

## Install

1. Install TrollStore on your device by following its official instructions.
2. Download `NoLowBatteryAlert.tipa` from the [latest release](../../releases/latest).
3. Optional: check the file against the SHA-256 listed in the release notes.

   ```powershell
   Get-FileHash NoLowBatteryAlert.tipa -Algorithm SHA256
   ```

   ```bash
   shasum -a 256 NoLowBatteryAlert.tipa
   ```

4. Open the `.tipa` with TrollStore (share sheet, then "Open in TrollStore", then Install).
5. Launch **Low Battery Off** from the home screen.

## Usage

1. Open the app and switch **Hide low-battery popup** ON.
2. Play your game. The 20% and 10% popups should no longer appear.
3. To get the normal behaviour back, open the app and switch it OFF.

The screen also shows:

- **Current value**: what the preferences system reports (`YES`, `NO` or `not set`).
- **File value**: what is stored in `/var/mobile/Library/Preferences/com.apple.springboard.plist`. This can read `nil` for a moment until iOS flushes the change to disk.
- **Respring (optional)**: restarts SpringBoard after a confirmation. Use it only if the popup still appears after switching ON.

Your battery level, Low Power Mode and the battery icon are not touched. Only the popup is suppressed.

## How it works

SpringBoard, the iOS home screen process, runs a handler whenever the battery level crosses a threshold. Reading the firmware shows that this handler first asks its power settings whether low-power alerts are hidden, and returns early if so, before it ever creates the alert.

In plain pseudocode (a description, not Apple's code):

```text
on battery level change:
    if power_settings.hide_low_power_alerts:
        return                       # no popup for the 20% or 10% step
    show low-battery alert for this level
```

That setting is backed by the preference key `SBHideLowPowerAlerts` in the `com.apple.springboard` domain. The app sets it with the public CFPreferences API:

```objc
CFPreferencesSetValue(CFSTR("SBHideLowPowerAlerts"),
                      kCFBooleanTrue,              // NULL to turn it off
                      CFSTR("com.apple.springboard"),
                      kCFPreferencesCurrentUser,
                      kCFPreferencesAnyHost);
CFPreferencesSynchronize(CFSTR("com.apple.springboard"),
                         kCFPreferencesCurrentUser,
                         kCFPreferencesAnyHost);
```

Writing another process's preferences needs more rights than a normal app has. TrollStore lets the app carry these entitlements (see [entitlements.plist](entitlements.plist)):

| Entitlement | Why |
|---|---|
| `platform-application` | Required by TrollStore apps that use privileged entitlements |
| `com.apple.private.security.no-sandbox` | Lets the app write another domain's preferences |
| `com.apple.security.exception.shared-preference.read-write` = `com.apple.springboard` | Names the domain it may write |

The app edits the setting through the preferences daemon on purpose. Editing the `.plist` file directly is unreliable because the daemon can overwrite it.

## Limitations and disclaimer

- Verified on one device and one iOS version, as described in [Compatibility](#compatibility).
- It only hides the popup. It does not stop your battery from draining, so keep an eye on the battery icon.
- It relies on an undocumented iOS setting. Apple can change or remove it in any update.
- You use it at your own risk. The change is reversible (switch OFF), and the app does not modify system files.
- This project is not affiliated with or endorsed by Apple, and has no connection to the TrollStore authors beyond being installable with their app.
- The in-app footer text still says "Untested on device." That text predates the 16.6.1 test and is out of date.

## Build from source

You need [Theos](https://theos.dev), an iOS SDK (built against iPhoneOS 16.5), and the TrollStore-compatible [ldid](https://github.com/opa334/ldid) fork from opa334. The author built it in WSL (Ubuntu 24.04).

```bash
export THEOS=$HOME/theos
make clean
make FINALPACKAGE=1 TARGET_CODESIGN=$HOME/opa-ldid/ldid
```

Then sign with the entitlements and package:

```bash
rm -rf pkg && mkdir pkg
cp -r .theos/obj/NoLowBatteryAlert.app pkg/
cp entitlements.plist pkg/
cd pkg
~/opa-ldid/ldid -Sentitlements.plist NoLowBatteryAlert.app/NoLowBatteryAlert
~/opa-ldid/ldid -s NoLowBatteryAlert.app
mkdir Payload && cp -r NoLowBatteryAlert.app Payload/
zip -qry NoLowBatteryAlert.tipa Payload
```

Things that matter:

- `ARCHS = arm64` only. An arm64e slice built with a Linux toolchain was a launch-crash risk, so it was dropped.
- Every plist in the bundle must be in **XML** format. TrollStore rejected an OpenStep-format plist with error 175.
- Pass `TARGET_CODESIGN` so Theos uses the opa334 ldid rather than another ldid earlier on your PATH.

## Project layout

```text
.
├── Makefile                 Theos application makefile
├── entitlements.plist       Entitlements embedded at signing time
├── Resources/               Info.plist and app icon PNGs
├── main.m, AppDelegate.*    App entry point
├── RootViewController.*     The UI and the preference logic
├── assets/icon_1024.png     Icon source
├── scripts/make_icons.py    Generates the icon sizes with Pillow
└── research/                Firmware analysis script (see below)
```

Code style: functions, methods and variables are `snake_case`. Apple framework names keep their own spelling.

## Research notes

The preference key was found by reading SpringBoard code in the dyld shared cache of the public firmware, then checked on a device. To see whether other versions behave the same, the shared caches of several iPhone 11 firmware images were extracted and the battery handler was located and disassembled with [Capstone](https://www.capstone-engine.org/).

- `research/analyze_cache.py` is the script used: it maps a shared-cache directory, finds the call sites of the relevant selectors and prints annotated disassembly.
- Versions where the handler matches: 14.0, 14.8, 15.0, 15.6.1, 16.0, 16.6.1, 17.0, 17.7.
- iOS 18 and 26 firmware images encrypt their system images (Apple Encrypted Archive), so they need an extra decryption step before analysis.

Usage:

```bash
python research/analyze_cache.py <path_to_dsc_directory>
```

The script is a research aid, not part of the app. It needs `capstone`. Its output is derived from Apple's binaries, so do not redistribute extracted caches.

## Troubleshooting

| Problem | What to try |
|---|---|
| TrollStore says installation failed (error 175) | The plists in the bundle must be XML. Rebuild as described above. |
| Popup still appears | Switch OFF, switch ON again, then use **Respring**. Confirm "Current value" shows `YES`. |
| "File value" shows `nil` | Normal for a short while. The preferences daemon writes to disk later. |
| Want to remove the effect | Switch OFF in the app. You can also delete the app. A key set earlier is cleared when you switch OFF, so do that first. |
| Works on one iOS version, not another | Open an issue with the iOS version and device model. |

## License

[MIT](LICENSE). Copyright (c) 2026 ndgthuan.
