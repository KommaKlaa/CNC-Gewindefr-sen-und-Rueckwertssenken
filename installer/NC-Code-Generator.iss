; NC-Code Generator – Inno Setup 6.3+ script
;
; Product metadata is injected by build_tools/create_installer.py
; via installer/defines.generated.iss (UTF-8) and/or /D defines.
; Source of truth: app_info.py
;
; AppId is the stable installer/upgrade identity.
; Never change AppId between releases (APP_ID_STABLE = YES).
;
; This script must not hardcode MyAppVersion.
; Offline only: no downloads, no Python install, no auto-updater.
; User data under {userappdata}\NC-Code Generator is never deleted.

#ifdef MyAppDefinesInclude
  #include MyAppDefinesInclude
#endif

#ifndef MyAppName
  #error MyAppName must be passed (defines include or /DMyAppName=...)
#endif
#ifndef MyAppVersion
  #error MyAppVersion must be passed (defines include or /DMyAppVersion=...)
#endif
#ifndef MyAppVersionInfo
  #error MyAppVersionInfo must be passed (defines include or /DMyAppVersionInfo=...)
#endif
#ifndef MyAppPublisher
  #error MyAppPublisher must be passed (defines include or /DMyAppPublisher=...)
#endif
#ifndef MyAppURL
  #error MyAppURL must be passed (defines include or /DMyAppURL=...)
#endif
#ifndef MyAppExeName
  #error MyAppExeName must be passed (defines include or /DMyAppExeName=...)
#endif
#ifndef MyAppId
  #error MyAppId must be passed (defines include or /DMyAppId=...)
#endif
#ifndef MyAppCopyright
  #error MyAppCopyright must be passed (defines include or /DMyAppCopyright=...)
#endif
#ifndef MyAppDescription
  #error MyAppDescription must be passed (defines include or /DMyAppDescription=...)
#endif
#ifndef PayloadDir
  #error PayloadDir must be passed (/DPayloadDir=...)
#endif
#ifndef OutputDir
  #error OutputDir must be passed (/DOutputDir=...)
#endif
#ifndef SetupIcon
  #define SetupIcon "..\assets\app_icon.ico"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=NC-Code-Generator-Setup-{#MyAppVersion}
SetupIconFile={#SetupIcon}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersionInfo}
VersionInfoProductVersion={#MyAppVersionInfo}
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright={#MyAppCopyright}
VersionInfoDescription={#MyAppDescription}
VersionInfoTextVersion={#MyAppVersion}
UsePreviousAppDir=yes
AllowNoIcons=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\app_icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; No [UninstallDelete] for {userappdata}:
; Safety-Notice acceptance and user projects must survive uninstall.
