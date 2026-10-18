TARGET := iphone:clang:16.5:14.0
ARCHS = arm64

include $(THEOS)/makefiles/common.mk

APPLICATION_NAME = NoLowBatteryAlert

NoLowBatteryAlert_FILES = main.m AppDelegate.m RootViewController.m
NoLowBatteryAlert_FRAMEWORKS = UIKit Foundation CoreFoundation
NoLowBatteryAlert_CFLAGS = -fobjc-arc -Wall -D__AUTHOR__=\"ndgthuan\" -D__BUILD_TS__=__DATE__
NoLowBatteryAlert_LDFLAGS = -Wl,-x
NoLowBatteryAlert_CODESIGN_FLAGS = -Sentitlements.plist

include $(THEOS_MAKE_PATH)/application.mk

after-NoLowBatteryAlert-all::
	@echo "Stripping debug symbols..."
	$(THEOS)/toolchain/*/bin/arm64-apple-darwin14-strip -x $(THEOS_STAGING_DIR)/Applications/NoLowBatteryAlert.app/NoLowBatteryAlert 2>/dev/null || strip -x $(THEOS_STAGING_DIR)/Applications/NoLowBatteryAlert.app/NoLowBatteryAlert 2>/dev/null || true
