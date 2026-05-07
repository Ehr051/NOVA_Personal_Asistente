#define AppName "Nova"
#define AppVersion "3.1"
#define AppPublisher "Ehr051"
#define AppURL "https://github.com/Ehr051/NOVA_Personal_Asistente"
#define AppExeName "Nova.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\Nova
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=Nova-Setup-{#AppVersion}
SetupIconFile=..\assets\nova.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Iconos adicionales:"
Name: "addtopath";      Description: "Agregar 'nova' al PATH del sistema (comando en consola)"; GroupDescription: "Opciones:"

[Files]
Source: "..\dist\Nova\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\nova.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\nova.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\AUDIO_SETUP_WINDOWS.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\Nova";                     Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\nova.ico"
Name: "{group}\Desinstalar Nova";         Filename: "{uninstallexe}"
Name: "{commondesktop}\Nova";             Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\nova.ico"; Tasks: desktopicon

[Registry]
; Agregar al PATH del sistema
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
; Crear .env si no existe (primera ejecución)
Filename: "{app}\{#AppExeName}"; Description: "Iniciar Nova ahora"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C setx PATH ""%PATH:{app};=%"" /M"; Flags: runhidden
