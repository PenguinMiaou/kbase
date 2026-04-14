[Setup]
AppName=KBase
AppVersion=0.6.3
AppPublisher=PenguinMiaou
AppPublisherURL=https://github.com/PenguinMiaou/kbase
DefaultDirName={autopf}\KBase
DefaultGroupName=KBase
OutputDir=..\dist
OutputBaseFilename=KBase-0.6.3-Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=KBase.ico
UninstallDisplayIcon={app}\KBase.exe
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\KBase\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\KBase"; Filename: "{app}\KBase.exe"
Name: "{autodesktop}\KBase"; Filename: "{app}\KBase.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\KBase.exe"; Description: "Launch KBase"; Flags: nowait postinstall skipifsilent
