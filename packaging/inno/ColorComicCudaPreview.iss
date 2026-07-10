; ColorComic CUDA Preview Windows desktop installer skeleton.
; Preview only: the official supported Windows installer remains CPU-only.
; Build only after CUDA preview validation:
;   ISCC.exe packaging\inno\ColorComicCudaPreview.iss

#define MyAppName "ColorComic CUDA Preview"
#define MyAppVersion "0.6.0"
#define MyAppPublisher "ColorComic"
#define MyAppExeName "ColorComicCudaPreview.exe"
#define MyAppIcon "..\..\static\img\colorcomic.ico"

[Setup]
AppId={{1F0D4951-2A2F-49DD-B905-28505D57C9E4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=output
OutputBaseFilename=ColorComic-Setup-{#MyAppVersion}-win64-cuda-preview
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
; The CUDA preview PyInstaller spec must keep model weights out of dist\ColorComicCudaPreview.
Source: "..\..\dist\ColorComicCudaPreview\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
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
