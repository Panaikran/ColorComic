; ColorComic Windows CPU desktop installer.
; Build with:
;   ISCC.exe packaging\inno\ColorComic.iss

#define MyAppName "ColorComic"
#define MyAppVersion "0.2.1"
#define MyAppPublisher "ColorComic"
#define MyAppExeName "ColorComic.exe"
#define MyAppIcon "..\..\static\img\colorcomic.ico"

[Setup]
AppId={{7D3E6C93-5726-4F99-A712-7C56AF830D4F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=output
OutputBaseFilename=ColorComic-Setup-{#MyAppVersion}-win64-cpu
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
SetupIconFile={#MyAppIcon}
UninstallDisplayIcon={app}\static\img\colorcomic.ico
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\ColorComic\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}\docs"; DestName: "PACKAGING_README.md"; Flags: ignoreversion
Source: "..\VALIDATION.md"; DestDir: "{app}\docs"; DestName: "VALIDATION.md"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\static\img\colorcomic.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\static\img\colorcomic.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
; Intentionally empty.
; Runtime data is preserved by default:
;   %LOCALAPPDATA%\ColorComic
; Users can delete that folder manually if they want to remove uploads,
; outputs, cached model weights, logs, and app configuration.
