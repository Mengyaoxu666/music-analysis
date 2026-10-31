#define AppVersion "1.0.0"

[Setup]
AppId={{93F5899D-B7AF-4677-8759-90B1E6576C5B}
AppName=Music Analysis
AppVersion={#AppVersion}
AppPublisher=Music Analysis Contributors
AppPublisherURL=https://github.com/Mengyaoxu666/music-analysis
DefaultDirName={localappdata}\Programs\MusicAnalysis
DefaultGroupName=Music Analysis
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
OutputDir=..\release
OutputBaseFilename=MusicAnalysis-{#AppVersion}-Windows-x64-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\MusicAnalysis.exe
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\MusicAnalysis\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Music Analysis"; Filename: "{app}\MusicAnalysis.exe"
Name: "{autodesktop}\Music Analysis"; Filename: "{app}\MusicAnalysis.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MusicAnalysis.exe"; Description: "Launch Music Analysis"; Flags: nowait postinstall skipifsilent
