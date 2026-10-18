#import "Watermark.h"
#import "Obfuscate.h"
#import "RootViewController.h"
#import <sys/types.h>
#import <sys/sysctl.h>
#import <signal.h>
#import <string.h>
#import <stdlib.h>
#import <errno.h>

static NSString *const PREFS_PATH = @"/var/mobile/Library/Preferences/com.apple.springboard.plist";

@interface RootViewController ()
@property (nonatomic, strong) UISwitch *toggle;
@property (nonatomic, strong) UILabel *current_label;
@property (nonatomic, strong) UILabel *file_label;
@property (nonatomic, strong) UILabel *message_label;
@end

@implementation RootViewController

- (UILabel *)make_label:(NSString *)text font:(UIFont *)font color:(UIColor *)color {
    UILabel *label = [[UILabel alloc] init];
    label.text = text;
    label.font = font;
    label.textColor = color;
    label.numberOfLines = 0;
    return label;
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = [UIColor systemBackgroundColor];

    UILabel *title = [self make_label:@"Low Battery Alert" font:[UIFont boldSystemFontOfSize:28] color:[UIColor labelColor]];

    UILabel *switch_label = [self make_label:@"Hide low-battery popup" font:[UIFont systemFontOfSize:17] color:[UIColor labelColor]];
    self.toggle = [[UISwitch alloc] init];
    [self.toggle addTarget:self action:@selector(toggle_changed:) forControlEvents:UIControlEventValueChanged];
    UIStackView *row = [[UIStackView alloc] initWithArrangedSubviews:@[switch_label, self.toggle]];
    row.axis = UILayoutConstraintAxisHorizontal;
    row.alignment = UIStackViewAlignmentCenter;

    self.current_label = [self make_label:@"" font:[UIFont monospacedSystemFontOfSize:15 weight:UIFontWeightRegular] color:[UIColor labelColor]];
    self.file_label = [self make_label:@"" font:[UIFont monospacedSystemFontOfSize:15 weight:UIFontWeightRegular] color:[UIColor secondaryLabelColor]];
    self.message_label = [self make_label:@"" font:[UIFont systemFontOfSize:15] color:[UIColor secondaryLabelColor]];

    UIButton *respring = [UIButton buttonWithType:UIButtonTypeSystem];
    [respring setTitle:@"Respring (optional)" forState:UIControlStateNormal];
    [respring addTarget:self action:@selector(respring_tapped) forControlEvents:UIControlEventTouchUpInside];

    UILabel *footer = [self make_label:@"Alert is skipped when battery crosses 20% / 10% while this is ON. Untested on device."
                                 font:[UIFont systemFontOfSize:13]
                                color:[UIColor secondaryLabelColor]];

    UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:@[title, row, self.current_label, self.file_label, respring, self.message_label, footer]];
    stack.axis = UILayoutConstraintAxisVertical;
    stack.spacing = 16;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:stack];

    UILayoutGuide *guide = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [stack.leadingAnchor constraintEqualToAnchor:guide.leadingAnchor constant:16],
        [stack.trailingAnchor constraintEqualToAnchor:guide.trailingAnchor constant:-16],
        [stack.topAnchor constraintEqualToAnchor:guide.topAnchor constant:24],
    ]];

    [self refresh];
}

- (void)toggle_changed:(UISwitch *)sender {
    CFStringRef key = CFSTR("SBHideLowPowerAlerts");
    CFStringRef domain = CFSTR("com.apple.springboard");
    if (sender.isOn) {
        CFPreferencesSetValue(key, kCFBooleanTrue, domain, kCFPreferencesCurrentUser, kCFPreferencesAnyHost);
    } else {
        CFPreferencesSetValue(key, NULL, domain, kCFPreferencesCurrentUser, kCFPreferencesAnyHost);
    }
    CFPreferencesSynchronize(domain, kCFPreferencesCurrentUser, kCFPreferencesAnyHost);
    [self refresh];
}

- (void)refresh {
    CFPropertyListRef current = CFPreferencesCopyValue(CFSTR("SBHideLowPowerAlerts"),
                                                       CFSTR("com.apple.springboard"),
                                                       kCFPreferencesCurrentUser,
                                                       kCFPreferencesAnyHost);
    NSString *text = @"not set";
    BOOL on = NO;
    if (current) {
        if (CFGetTypeID(current) == CFBooleanGetTypeID()) {
            on = CFBooleanGetValue(current);
            text = on ? @"YES" : @"NO";
        } else {
            text = [NSString stringWithFormat:@"%@ (not a boolean)", (__bridge id)current];
        }
        CFRelease(current);
    }
    self.toggle.on = on;
    self.current_label.text = [NSString stringWithFormat:@"Current value: %@", text];

    NSDictionary *dict = [NSDictionary dictionaryWithContentsOfFile:PREFS_PATH];
    id file_value = dict[@"SBHideLowPowerAlerts"];
    NSString *file_text;
    if (!dict) {
        file_text = @"file not readable";
    } else if ([file_value isKindOfClass:[NSNumber class]]) {
        file_text = [file_value boolValue] ? @"YES" : @"NO";
    } else if (file_value) {
        file_text = [file_value description];
    } else {
        file_text = @"nil (not in file yet)";
    }
    self.file_label.text = [NSString stringWithFormat:@"File value: %@", file_text];
}

- (void)respring_tapped {
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"Respring now?"
                                                                   message:@"This kills SpringBoard. Unsaved state on screen is lost."
                                                            preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Respring" style:UIAlertActionStyleDestructive handler:^(UIAlertAction *action) {
        [self respring];
    }]];
    [self presentViewController:alert animated:YES completion:nil];
}

- (void)respring {
    int mib[4] = { CTL_KERN, KERN_PROC, KERN_PROC_ALL, 0 };
    size_t size = 0;
    if (sysctl(mib, 4, NULL, &size, NULL, 0) != 0) {
        self.message_label.text = @"sysctl failed (size query)";
        return;
    }
    size += 16 * sizeof(struct kinfo_proc); // slack for processes started since the size query
    struct kinfo_proc *procs = malloc(size);
    if (!procs) {
        self.message_label.text = @"malloc failed";
        return;
    }
    if (sysctl(mib, 4, procs, &size, NULL, 0) != 0) {
        free(procs);
        self.message_label.text = @"sysctl failed (process list)";
        return;
    }
    pid_t target = 0;
    size_t count = size / sizeof(struct kinfo_proc);
    for (size_t i = 0; i < count; i++) {
        if (strcmp(procs[i].kp_proc.p_comm, "SpringBoard") == 0) {
            target = procs[i].kp_proc.p_pid;
            break;
        }
    }
    free(procs);
    if (target <= 0) {
        self.message_label.text = @"SpringBoard process not found";
        return;
    }
    if (kill(target, SIGKILL) != 0) {
        self.message_label.text = [NSString stringWithFormat:@"kill(%d) failed, errno %d", (int)target, errno];
        return;
    }
    self.message_label.text = [NSString stringWithFormat:@"Sent SIGKILL to SpringBoard (pid %d)", (int)target];
}

@end
