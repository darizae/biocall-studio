; Inno Setup 6 x86-64 installer. Compile on Windows *after* source freeze.
; Source is the native Windows PyInstaller onedir folder, never a Linux binary.
#define StudioVersion "0.1.0a1"
#define AppRoot "..\..\dist\native-windows\BioCall Studio"

[Setup]
AppId={{D2F7896C-9CB4-4580-8A41-A02D3AB332D5}
AppName=BioCall Studio
AppVersion={#StudioVersion}
AppVerName=BioCall Studio {#StudioVersion}
AppPublisher=BioCall Studio
DefaultDirName={autopf}\BioCall Studio
DefaultGroupName=BioCall Studio
UninstallDisplayName=BioCall Studio
UninstallDisplayIcon={app}\BioCall Studio.exe
SetupIconFile=..\..\assets\branding\icons\icon.ico
OutputDir=..\..\dist\native-windows-installer
OutputBaseFilename=BioCall-Studio-{#StudioVersion}-windows-x86_64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
DisableProgramGroupPage=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
; Never add [UninstallDelete] pointing to {userappdata}, Collections, recordings,
; Review data, Models, Results or user-chosen export destinations.

[Files]
Source: "{#AppRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\BioCall Studio"; Filename: "{app}\BioCall Studio.exe"
Name: "{autodesktop}\BioCall Studio"; Filename: "{app}\BioCall Studio.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\BioCall Studio.exe"; Description: "Launch BioCall Studio"; Flags: nowait postinstall skipifsilent
