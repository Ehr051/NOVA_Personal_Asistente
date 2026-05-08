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
DisableDirPage=no
DisableProgramGroupPage=yes
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
Name: "{commondesktop}\Nova";     Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\nova.ico"; Tasks: desktopicon; WorkingDir: "{app}"

[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
; Lanzar con cmd /k para que la ventana quede abierta si Nova crashea
Filename: "cmd.exe"; Parameters: "/k ""{app}\{#AppExeName}"""; Description: "Iniciar Nova ahora"; Flags: nowait postinstall skipifsilent

[Code]
var
  LLMPage:           TWizardPage;
  IntegPage:         TWizardPage;

  GroqEdit:          TEdit;
  OpenRouterEdit:    TEdit;
  AnthropicEdit:     TEdit;
  CerebrasEdit:      TEdit;
  MistralEdit:       TEdit;
  DeepSeekEdit:      TEdit;

  TelegramTokenEdit: TEdit;
  TelegramChatEdit:  TEdit;
  ObsidianEdit:      TEdit;
  GitHubEdit:        TEdit;

// ── Helper: añade un par Label+Edit a una página ──────────────────────────────
procedure AddField(Page: TWizardPage; Caption: String; var EditCtrl: TEdit; var Y: Integer);
var
  Lbl: TLabel;
begin
  Lbl := TLabel.Create(WizardForm);
  Lbl.Parent  := Page.Surface;
  Lbl.Caption := Caption;
  Lbl.Top     := Y;
  Lbl.Left    := 0;
  Lbl.AutoSize := True;
  Y := Y + 16;

  EditCtrl := TEdit.Create(WizardForm);
  EditCtrl.Parent := Page.Surface;
  EditCtrl.Top    := Y;
  EditCtrl.Left   := 0;
  EditCtrl.Width  := Page.SurfaceWidth;
  EditCtrl.Text   := '';
  Y := Y + 26;
end;

// ── Página personalizada de API Keys ──────────────────────────────────────────
procedure InitializeWizard;
var
  Y:    Integer;
  Note: TLabel;
begin
  // ── Página 1: LLM Providers ─────────────────────────────────────────────────
  LLMPage := CreateCustomPage(wpSelectTasks,
    'Proveedores LLM',
    'Ingresá las claves de los modelos de lenguaje que querés usar.');

  Y := 0;

  Note := TLabel.Create(WizardForm);
  Note.Parent  := LLMPage.Surface;
  Note.Caption :=
    'Al menos uno recomendado. Groq y Cerebras son gratis.' + #13#10 +
    'Dejá vacío cualquier campo para configurarlo después.';
  Note.AutoSize := True;
  Note.Top  := Y;
  Note.Left := 0;
  Note.Width := LLMPage.SurfaceWidth;
  Y := Y + 34;

  AddField(LLMPage, 'Groq API Key  (gratis: console.groq.com)',           GroqEdit,       Y);
  AddField(LLMPage, 'OpenRouter API Key  (gratis: openrouter.ai)',         OpenRouterEdit, Y);
  AddField(LLMPage, 'Anthropic API Key  (opcional, de pago)',              AnthropicEdit,  Y);
  AddField(LLMPage, 'Cerebras API Key  (gratis: inference.cerebras.ai)',   CerebrasEdit,   Y);
  AddField(LLMPage, 'Mistral API Key  (free tier: console.mistral.ai)',    MistralEdit,    Y);
  AddField(LLMPage, 'DeepSeek API Key  (barato: platform.deepseek.com)',   DeepSeekEdit,   Y);

  // ── Página 2: Integraciones ──────────────────────────────────────────────────
  IntegPage := CreateCustomPage(LLMPage.ID,
    'Integraciones',
    'Servicios opcionales que Nova puede usar para notificaciones y memoria.');

  Y := 0;

  Note := TLabel.Create(WizardForm);
  Note.Parent  := IntegPage.Surface;
  Note.Caption := 'Todos opcionales — podés configurarlos después.';
  Note.AutoSize := True;
  Note.Top  := Y;
  Note.Left := 0;
  Note.Width := IntegPage.SurfaceWidth;
  Y := Y + 26;

  AddField(IntegPage, 'Telegram Bot Token  (ej: 123456789:AAF...)',        TelegramTokenEdit, Y);
  AddField(IntegPage, 'Telegram Chat ID',                                   TelegramChatEdit,  Y);
  AddField(IntegPage, 'Obsidian API Key  (plugin Local REST API)',          ObsidianEdit,      Y);
  AddField(IntegPage, 'GitHub Token  (ej: ghp_...)',                        GitHubEdit,        Y);
end;

// ── Escribir .env después de copiar los archivos ──────────────────────────────
procedure WriteEnvFile;
var
  EnvPath, Content: String;
begin
  EnvPath := ExpandConstant('{app}\.env');

  Content :=
    'GROQ_API_KEY='         + Trim(GroqEdit.Text)          + #13#10 +
    'OPENROUTER_API_KEY='   + Trim(OpenRouterEdit.Text)     + #13#10 +
    'ANTHROPIC_API_KEY='    + Trim(AnthropicEdit.Text)      + #13#10 +
    'CEREBRAS_API_KEY='     + Trim(CerebrasEdit.Text)       + #13#10 +
    'MISTRAL_API_KEY='      + Trim(MistralEdit.Text)        + #13#10 +
    'DEEPSEEK_API_KEY='     + Trim(DeepSeekEdit.Text)       + #13#10 +
    'TELEGRAM_BOT_TOKEN='   + Trim(TelegramTokenEdit.Text)  + #13#10 +
    'TELEGRAM_CHAT_ID='     + Trim(TelegramChatEdit.Text)   + #13#10 +
    'OBSIDIAN_API_KEY='     + Trim(ObsidianEdit.Text)       + #13#10 +
    'GITHUB_TOKEN='         + Trim(GitHubEdit.Text)         + #13#10 +
    'OLLAMA_BASE_URL=http://127.0.0.1:11434/v1'             + #13#10 +
    'ASSISTANT_NAME=Nova'                                   + #13#10 +
    'NOVA_VOICE=Reed'                                       + #13#10 +
    'SESSION_BUDGET_USD=0.10'                               + #13#10;

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
