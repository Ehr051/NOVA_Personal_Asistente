#ifndef AppVersion
  #define AppVersion "3.2"
#endif
#define AppName      "Nova"
#define AppPublisher "Ehr051"
#define AppURL       "https://github.com/Ehr051/NOVA_Personal_Asistente"
#define AppExeName   "Nova.exe"

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
OutputBaseFilename=Nova-Setup
SetupIconFile=..\assets\nova.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\nova.ico

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Iconos adicionales:"
Name: "addtopath";   Description: "Agregar 'nova' al PATH del sistema"; GroupDescription: "Opciones:"

[Files]
Source: "..\dist\Nova\*";     DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\nova.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\nova.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";       DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Nova";             Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\nova.ico"
Name: "{group}\Desinstalar Nova"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Nova";     Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\nova.ico"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Iniciar Nova ahora"; Flags: nowait postinstall skipifsilent

[Code]
var
  APIKeyPage: TWizardPage;
  GroqEdit:        TEdit;
  OpenRouterEdit:  TEdit;
  AnthropicEdit:   TEdit;
  GroqLabel:       TLabel;
  OpenRouterLabel: TLabel;
  AnthropicLabel:  TLabel;
  NoteLabel:       TLabel;

// ── Página personalizada de API Keys ──────────────────────────────────────────
procedure InitializeWizard;
var
  Y: Integer;
begin
  APIKeyPage := CreateCustomPage(wpSelectTasks,
    'Configurar API Keys',
    'Ingresá tus claves de acceso a los modelos de lenguaje.');

  Y := 0;

  NoteLabel := TLabel.Create(WizardForm);
  NoteLabel.Parent := APIKeyPage.Surface;
  NoteLabel.Caption :=
    'Podés dejar cualquier campo vacío y configurarlo después diciendo:' + #13#10 +
    '"nova, mi api de groq es gsk_xxxx"';
  NoteLabel.AutoSize := True;
  NoteLabel.Top := Y;
  NoteLabel.Left := 0;
  NoteLabel.Width := APIKeyPage.SurfaceWidth;
  Y := Y + 36;

  // Groq
  GroqLabel := TLabel.Create(WizardForm);
  GroqLabel.Parent := APIKeyPage.Surface;
  GroqLabel.Caption := 'Groq API Key  (gratis: console.groq.com)';
  GroqLabel.Top := Y;
  GroqLabel.Left := 0;
  GroqLabel.AutoSize := True;
  Y := Y + 18;

  GroqEdit := TEdit.Create(WizardForm);
  GroqEdit.Parent := APIKeyPage.Surface;
  GroqEdit.Top := Y;
  GroqEdit.Left := 0;
  GroqEdit.Width := APIKeyPage.SurfaceWidth;
  GroqEdit.Text := '';
  GroqEdit.PasswordChar := #0;
  Y := Y + 28;

  // OpenRouter
  OpenRouterLabel := TLabel.Create(WizardForm);
  OpenRouterLabel.Parent := APIKeyPage.Surface;
  OpenRouterLabel.Caption := 'OpenRouter API Key  (gratis: openrouter.ai)';
  OpenRouterLabel.Top := Y;
  OpenRouterLabel.Left := 0;
  OpenRouterLabel.AutoSize := True;
  Y := Y + 18;

  OpenRouterEdit := TEdit.Create(WizardForm);
  OpenRouterEdit.Parent := APIKeyPage.Surface;
  OpenRouterEdit.Top := Y;
  OpenRouterEdit.Left := 0;
  OpenRouterEdit.Width := APIKeyPage.SurfaceWidth;
  OpenRouterEdit.Text := '';
  Y := Y + 28;

  // Anthropic
  AnthropicLabel := TLabel.Create(WizardForm);
  AnthropicLabel.Parent := APIKeyPage.Surface;
  AnthropicLabel.Caption := 'Anthropic API Key  (opcional, de pago)';
  AnthropicLabel.Top := Y;
  AnthropicLabel.Left := 0;
  AnthropicLabel.AutoSize := True;
  Y := Y + 18;

  AnthropicEdit := TEdit.Create(WizardForm);
  AnthropicEdit.Parent := APIKeyPage.Surface;
  AnthropicEdit.Top := Y;
  AnthropicEdit.Left := 0;
  AnthropicEdit.Width := APIKeyPage.SurfaceWidth;
  AnthropicEdit.Text := '';
end;

// ── Escribir .env después de copiar los archivos ──────────────────────────────
procedure WriteEnvFile;
var
  EnvPath, Content: String;
  GroqKey, OpenRouterKey, AnthropicKey: String;
begin
  EnvPath := ExpandConstant('{app}\.env');

  GroqKey       := Trim(GroqEdit.Text);
  OpenRouterKey := Trim(OpenRouterEdit.Text);
  AnthropicKey  := Trim(AnthropicEdit.Text);

  // Valores vacíos dejan el campo en blanco (Nova usa Ollama local de fallback)
  Content :=
    'GROQ_API_KEY='       + GroqKey       + #13#10 +
    'OPENROUTER_API_KEY=' + OpenRouterKey + #13#10 +
    'ANTHROPIC_API_KEY='  + AnthropicKey  + #13#10 +
    'OLLAMA_BASE_URL=http://127.0.0.1:11434/v1' + #13#10 +
    'ASSISTANT_NAME=Nova' + #13#10 +
    'NOVA_VOICE=Reed'     + #13#10 +
    'SESSION_BUDGET_USD=0.10' + #13#10;

  SaveStringToFile(EnvPath, Content, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteEnvFile;
end;

// ── PATH helper ───────────────────────────────────────────────────────────────
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
