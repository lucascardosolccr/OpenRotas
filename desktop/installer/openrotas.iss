; ============================================================================
;  OpenRotas Desktop — Instalador (Inno Setup 6)
;  Empacota a pasta ONEDIR gerada pelo PyInstaller num instalador profissional
;  "OpenRotas Setup.exe": atalhos, diretório de dados do usuário, desinstalador,
;  e teste de integridade pós-instalação.
;
;  Pré-requisito: ter rodado  pyinstaller packaging\launcher.spec  (gera build\dist\OpenRotas\).
;  Compilar:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\openrotas.iss
;  (ou abra este .iss no Inno Setup e clique em Compile)
; ============================================================================

#define AppName "OpenRotas"
; A versão vem de desktop_config.APP_VERSION (fonte única — §19/§38), passada por
;   ISCC /DAppVersion=<x>  (build.ps1 e o workflow fazem isso). Fallback se não vier.
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppPublisher "Lucas Cruz"
#define AppExe "OpenRotas.exe"

[Setup]
AppId={{B7E2B6B0-0C3E-4E7A-9E5E-0PENROTAS0001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Dados do usuário (cache/config/logs) ficam FORA da pasta de instalação — ver §19/§31.
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=OpenRotas Setup
OutputDir=dist_installer
PrivilegesRequired=lowest
; SetupIconFile=openrotas.ico

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
; A pasta onedir inteira do PyInstaller (app + runtime Python + libs + bases embarcadas).
; Caminho relativo à pasta deste .iss (desktop\installer\) → sobe um nível até desktop\build\...
Source: "..\build\dist\OpenRotas\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Exemplo de configuração (o app cria o real em %LOCALAPPDATA% no 1º uso).
Source: "..\config\desktop.example.json"; DestDir: "{app}\config"; Flags: ignoreversion

[Dirs]
; Diretório PERSISTENTE de dados do usuário (sobrevive a updates/desinstalação controlada).
Name: "{localappdata}\{#AppName}"; Flags: uninsneveruninstall
Name: "{localappdata}\{#AppName}\cache"; Flags: uninsneveruninstall
Name: "{localappdata}\{#AppName}\config"; Flags: uninsneveruninstall
Name: "{localappdata}\{#AppName}\logs"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Diagnóstico do OpenRotas"; Filename: "{app}\{#AppExe}"; Parameters: "--diagnostico"
Name: "{group}\Recursos do OpenRotas"; Filename: "{app}\{#AppExe}"; Parameters: "--recursos"
Name: "{group}\Verificar atualizações"; Filename: "{app}\{#AppExe}"; Parameters: "--atualizar"
Name: "{group}\Reparar instalação"; Filename: "{app}\{#AppExe}"; Parameters: "--reparar"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Teste de integridade pós-instalação (§18/§30): roda o diagnóstico silencioso; se falhar,
; o usuário é avisado mas a instalação não é abortada (ele pode reparar depois).
Filename: "{app}\{#AppExe}"; Parameters: "--diagnostico --silencioso"; StatusMsg: "Validando a instalação..."; Flags: runhidden; Check: SempreExecutar
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName} agora"; Flags: nowait postinstall skipifsilent

[Code]
function SempreExecutar: Boolean;
begin
  Result := True;
end;
